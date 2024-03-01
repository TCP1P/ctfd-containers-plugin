from __future__ import division

import time
import json
import datetime
import math

from flask import Blueprint, request, Flask, render_template, url_for, redirect, flash

from CTFd.models import db, Solves
from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import CHALLENGE_CLASSES, BaseChallenge
from CTFd.utils.decorators import authed_only, admins_only, during_ctf_time_only, ratelimit, require_verified_emails
from CTFd.utils.user import get_current_user
from CTFd.utils.modes import get_model
from CTFd.utils.config import is_users_mode

from .models import ContainerChallengeModel, ContainerInfoModel, ContainerSettingsModel
from .container_manager import ContainerManager, ContainerException


import os

DOCKER_BASE_URL = os.environ.get("DOCKER_BASE_URL")
DOCKER_HOSTNAME = os.environ.get("DOCKER_HOSTNAME")
CONTAINER_EXPIRATION = os.environ.get("CONTAINER_EXPIRATION")
CONTAINER_MAXMEMORY = os.environ.get("CONTAINER_MAXMEMORY")
CONTAINER_MAXCPU = os.environ.get("CONTAINER_MAXCPU")

def init():
    if DOCKER_HOSTNAME is None:
        return
    if CONTAINER_EXPIRATION is None:
        return
    if CONTAINER_MAXMEMORY is None:
        return
    if CONTAINER_MAXCPU is None:
        return
    docker_base_url = ContainerSettingsModel.query.filter_by(
        key="docker_base_url").first()

    docker_hostname = ContainerSettingsModel.query.filter_by(
        key="docker_hostname").first()

    container_expiration = ContainerSettingsModel.query.filter_by(
        key="container_expiration").first()

    container_maxmemory = ContainerSettingsModel.query.filter_by(
        key="container_maxmemory").first()

    container_maxcpu = ContainerSettingsModel.query.filter_by(
        key="container_maxcpu").first()

    if docker_base_url is None:
        docker_base_url = ContainerSettingsModel(key="docker_base_url", value=DOCKER_BASE_URL)
        db.session.add(docker_base_url)
    else:
        docker_base_url.value = DOCKER_BASE_URL

    if docker_hostname is None:
        docker_hostname = ContainerSettingsModel(key="docker_hostname", value=DOCKER_HOSTNAME)
        db.session.add(docker_hostname)
    else:
        docker_hostname.value = DOCKER_HOSTNAME

    if container_expiration is None:
        container_expiration = ContainerSettingsModel(key="container_expiration", value=CONTAINER_EXPIRATION)
        db.session.add(container_expiration)
    else:
        container_expiration.value = CONTAINER_EXPIRATION

    if container_maxmemory is None:
        container_maxmemory = ContainerSettingsModel(key="container_maxmemory", value=CONTAINER_MAXMEMORY)
        db.session.add(container_maxmemory)
    else:
        container_maxmemory.value = CONTAINER_MAXMEMORY

    if container_maxcpu is None:
        container_maxcpu = ContainerSettingsModel(key="container_maxcpu", value=CONTAINER_MAXCPU)
        db.session.add(container_maxcpu)
    else:
       container_maxcpu.value = CONTAINER_MAXCPU

    db.session.commit()

init()

class ContainerChallenge(BaseChallenge):
    id = "container"
    name = "container"
    templates = {
        "create": "/plugins/containers/assets/create.html",
        "update": "/plugins/containers/assets/update.html",
        "view": "/plugins/containers/assets/view.html",
    }
    scripts = {
        "create": "/plugins/containers/assets/create.js",
        "update": "/plugins/containers/assets/update.js",
        "view": "/plugins/containers/assets/view.js",
    }
    route = "/plugins/containers/assets/"

    challenge_model = ContainerChallengeModel

    @classmethod
    def read(cls, challenge):
        """
        This method is in used to access the data of a challenge in a format processable by the front end.

        :param challenge:
        :return: Challenge object, data dictionary to be returned to the user
        """
        data = {
            "id": challenge.id,
            "name": challenge.name,
            "value": challenge.value,
            "image": challenge.image,
            "port": challenge.port,
            "command": challenge.command,
            "volumes": challenge.volumes,
            "limit": challenge.limit,
            "connection_format": challenge.connection_format,
            "initial": challenge.initial,
            "decay": challenge.decay,
            "minimum": challenge.minimum,
            "description": challenge.description,
            "connection_info": challenge.connection_info,
            "category": challenge.category,
            "state": challenge.state,
            "max_attempts": challenge.max_attempts,
            "type": challenge.type,
            "type_data": {
                "id": cls.id,
                "name": cls.name,
                "templates": cls.templates,
                "scripts": cls.scripts,
            },
        }
        return data

    @classmethod
    def calculate_value(cls, challenge):
        Model = get_model()

        solve_count = (
            Solves.query.join(Model, Solves.account_id == Model.id)
            .filter(
                Solves.challenge_id == challenge.id,
                Model.hidden == False,
                Model.banned == False,
            )
            .count()
        )

        if solve_count != 0:
            solve_count -= 1

        value = (
            ((challenge.minimum - challenge.initial) / (challenge.decay ** 2))
            * (solve_count ** 2)
        ) + challenge.initial

        value = math.ceil(value)

        if value < challenge.minimum:
            value = challenge.minimum

        challenge.value = value
        db.session.commit()
        return challenge

    @classmethod
    def update(cls, challenge, request):
        """
        This method is used to update the information associated with a challenge. This should be kept strictly to the
        Challenges table and any child tables.
        :param challenge:
        :param request:
        :return:
        """
        data = request.form or request.get_json()

        for attr, value in data.items():
            if attr in ("initial", "minimum", "decay"):
                value = float(value)
            setattr(challenge, attr, value)

        return ContainerChallenge.calculate_value(challenge)

    @classmethod
    def solve(cls, user, team, challenge, request):
        super().solve(user, team, challenge, request)

        ContainerChallenge.calculate_value(challenge)


def settings_to_dict(settings):
    return {
        setting.key: setting.value for setting in settings
    }


def load(app: Flask):
    app.db.create_all()
    init()
    CHALLENGE_CLASSES["container"] = ContainerChallenge
    register_plugin_assets_directory(
        app, base_path="/plugins/containers/assets/"
    )

    container_settings = settings_to_dict(ContainerSettingsModel.query.all())
    container_manager = ContainerManager(container_settings, app)

    containers_bp = Blueprint(
        'containers', __name__, template_folder='templates', static_folder='assets', url_prefix='/containers')

    @containers_bp.app_template_filter("format_time")
    def format_time_filter(unix_seconds):
        return datetime.datetime.fromtimestamp(unix_seconds, tz=datetime.datetime.now(
            datetime.timezone.utc).astimezone().tzinfo).isoformat()

    def kill_container(container_id):
        container: ContainerInfoModel = ContainerInfoModel.query.filter_by(
            container_id=container_id).first()

        try:
            container_manager.kill_container(container_id)
        except ContainerException:
            return {"error": "Docker is not initialized. Please check your settings."}

        db.session.delete(container)

        db.session.commit()
        return {"success": "Container killed!"}

    def renew_container(chal_id, team_id):
        challenge = ContainerChallenge.challenge_model.query.filter_by(
            id=chal_id).first()

        if challenge is None:
            return {"error": "Challenge was not found."}, 400

        running_containers = ContainerInfoModel.query.filter_by(challenge_id=challenge.id, team_id=team_id)
        running_container = running_containers.first()

        if running_container is None:
            return {"error": "Container not found, try resetting the container."}

        try:
            running_container.expires = int(time.time() + container_manager.expiration_seconds)
            db.session.commit()
        except ContainerException:
            return {"error": "Database error occurred, please try again."}

        return {"success": "Container renewed", "expires": running_container.expires}

    def create_container(chal_id, team_id):
        challenge = ContainerChallenge.challenge_model.query.filter_by(id=chal_id).first()

        if challenge is None:
            return {"error": "Challenge was not found."}, 400

        running_containers = ContainerInfoModel.query.filter_by(challenge_id=challenge.id, team_id=team_id)
        running_container = running_containers.first()

        if running_container:
            try:
                if container_manager.is_container_running(running_container.container_id):
                    host = container_manager.settings.get("docker_hostname", "")
                    port = running_container.port

                    conn = str(host) + ':' + str(port)
                    if challenge.connection_format:
                        if '{HOST}' in challenge.connection_format and '{PORT}' in challenge.connection_format:
                            conn = challenge.connection_format.replace('{HOST}', host).replace('{PORT}', str(port))

                    return json.dumps({
                        "status": "already_running",
                        "connection": conn,
                        "expires": running_container.expires
                    })
                else:
                    running_containers.delete()
                    db.session.commit()
            except ContainerException as err:
                return {"error": str(err)}, 500

        if ContainerInfoModel.query.filter_by(challenge_id=challenge.id).count() >= challenge.limit and challenge.limit != 0:
            return {"error": "This challenge currently has exceeded instance limitation, please try again later."}, 400

        try:
            created_container = container_manager.create_container(challenge.image, challenge.port, challenge.command, challenge.volumes)
        except ContainerException as err:
            return {"error": str(err)}

        port = None
        try:
            port = container_manager.get_container_port(created_container.id)
            if port is None:
                for i in range(10):
                    port = container_manager.get_container_port(created_container.id)
                    if port is not None:
                        break
                    time.sleep(0.5)
        except:
            pass

        if port is None:
            try:
                container_manager.kill_container(created_container.id)
            except ContainerException:
                pass

            return json.dumps({
                "status": "error",
                "error": "Could not get port, please re-open this challenge or try again later."
            })

        expires = int(time.time() + container_manager.expiration_seconds)

        new_container = ContainerInfoModel(
            container_id=created_container.id,
            challenge_id=challenge.id,
            team_id=team_id,
            port=port,
            timestamp=int(time.time()),
            expires=expires
        )
        db.session.add(new_container)
        db.session.commit()

        host = container_manager.settings.get("docker_hostname", "")
        port = port

        conn = str(host) + ':' + str(port)
        if challenge.connection_format:
            if '{HOST}' in challenge.connection_format and '{PORT}' in challenge.connection_format:
                conn = challenge.connection_format.replace('{HOST}', host).replace('{PORT}', str(port))

        return json.dumps({
            "status": "created",
            "connection": conn,
            "expires": expires
        })

    @containers_bp.route('/api/request', methods=['POST'])
    @authed_only
    @during_ctf_time_only
    @require_verified_emails
    @ratelimit(method="POST", limit=6, interval=60)
    def route_request_container():
        user = get_current_user()

        if request.json is None:
            return {"error": "Invalid request."}, 400

        if request.json.get("chal_id", None) is None:
            return {"error": "Invalid request."}, 400

        if user is None:
            return {"error": "User was not found."}, 400

        _id = None
        if is_users_mode():
            _id = user.id
        else:
            _id = user.team.id

        try:
            return create_container(request.json.get("chal_id"), _id)
        except ContainerException as err:
            return {"error": str(err)}, 500

    @containers_bp.route('/api/renew', methods=['POST'])
    @authed_only
    @during_ctf_time_only
    @require_verified_emails
    @ratelimit(method="POST", limit=6, interval=60)
    def route_renew_container():
        user = get_current_user()

        if request.json is None:
            return {"error": "Invalid request."}, 400

        if request.json.get("chal_id", None) is None:
            return {"error": "Invalid request."}, 400

        if user is None:
            return {"error": "User was not found."}, 400

        _id = None
        if is_users_mode():
            _id = user.id
        else:
            _id = user.team.id

        try:
            return renew_container(request.json.get("chal_id"), _id)
        except ContainerException as err:
            return {"error": str(err)}, 500

    @containers_bp.route('/api/reset', methods=['POST'])
    @authed_only
    @during_ctf_time_only
    @require_verified_emails
    @ratelimit(method="POST", limit=6, interval=60)
    def route_restart_container():
        user = get_current_user()

        if request.json is None:
            return {"error": "Invalid request."}, 400

        if request.json.get("chal_id", None) is None:
            return {"error": "Invalid request."}, 400

        if user is None:
            return {"error": "User was not found."}, 400

        _id = None
        if is_users_mode():
            _id = user.id
        else:
            _id = user.team.id

        running_container = ContainerInfoModel.query.filter_by(challenge_id=request.json.get("chal_id"), team_id=_id).first()
        if running_container:
            kill_container(running_container.container_id)

        return create_container(request.json.get("chal_id"), _id)

    @containers_bp.route('/api/stop', methods=['POST'])
    @authed_only
    @during_ctf_time_only
    @require_verified_emails
    @ratelimit(method="POST", limit=6, interval=60)
    def route_stop_container():
        user = get_current_user()

        if request.json is None:
            return {"error": "Invalid request."}, 400

        if request.json.get("chal_id", None) is None:
            return {"error": "Invalid request."}, 400

        if user is None:
            return {"error": "User was not found."}, 400

        _id = None
        if is_users_mode():
            _id = user.id
        else:
            _id = user.team.id

        running_container = ContainerInfoModel.query.filter_by(challenge_id=request.json.get("chal_id"), team_id=_id).first()
        if running_container:
            return kill_container(running_container.container_id)

        return {"error": "No container found"}, 400

    @containers_bp.route('/api/kill', methods=['POST'])
    @admins_only
    def route_kill_container():
        if request.json is None:
            return {"error": "Invalid request."}, 400

        if request.json.get("container_id", None) is None:
            return {"error": "Invalid request."}, 400

        return kill_container(request.json.get("container_id"))

    @containers_bp.route('/api/purge', methods=['POST'])
    @admins_only
    def route_purge_containers():
        containers: "list[ContainerInfoModel]" = ContainerInfoModel.query.all()
        for container in containers:
            try:
                kill_container(container.container_id)
            except ContainerException:
                pass
        return {"success": "Containers purged!"}, 200

    @containers_bp.route('/api/images', methods=['GET'])
    @admins_only
    def route_get_images():
        try:
            images = container_manager.get_images()
        except ContainerException as err:
            return {"error": str(err)}

        return {"images": images}

    @containers_bp.route('/api/settings/update', methods=['POST'])
    @admins_only
    def route_update_settings():
        if request.form.get("docker_base_url") is None:
            return {"error": "Invalid request."}, 400

        if request.form.get("docker_hostname") is None:
            return {"error": "Invalid request."}, 400

        if request.form.get("container_expiration") is None:
            return {"error": "Invalid request."}, 400

        if request.form.get("container_maxmemory") is None:
            return {"error": "Invalid request."}, 400

        if request.form.get("container_maxcpu") is None:
            return {"error": "Invalid request."}, 400

        docker_base_url = ContainerSettingsModel.query.filter_by(key="docker_base_url").first()
        docker_hostname = ContainerSettingsModel.query.filter_by(key="docker_hostname").first()
        container_expiration = ContainerSettingsModel.query.filter_by(key="container_expiration").first()
        container_maxmemory = ContainerSettingsModel.query.filter_by(key="container_maxmemory").first()
        container_maxcpu = ContainerSettingsModel.query.filter_by(key="container_maxcpu").first()

        if docker_base_url is None:
            docker_base_url = ContainerSettingsModel(key="docker_base_url", value=request.form.get("docker_base_url"))
            db.session.add(docker_base_url)
        else:
            docker_base_url.value = request.form.get("docker_base_url")

        if docker_hostname is None:
            docker_hostname = ContainerSettingsModel(key="docker_hostname", value=request.form.get("docker_hostname"))
            db.session.add(docker_hostname)
        else:
            docker_hostname.value = request.form.get("docker_hostname")

        if container_expiration is None:
            container_expiration = ContainerSettingsModel(key="container_expiration", value=request.form.get("container_expiration"))
            db.session.add(container_expiration)
        else:
            container_expiration.value = request.form.get("container_expiration")

        if container_maxmemory is None:
            container_maxmemory = ContainerSettingsModel(key="container_maxmemory", value=request.form.get("container_maxmemory"))
            db.session.add(container_maxmemory)
        else:
            container_maxmemory.value = request.form.get("container_maxmemory")

        if container_maxcpu is None:
            container_maxcpu = ContainerSettingsModel(key="container_maxcpu", value=request.form.get("container_maxcpu"))
            db.session.add(container_maxcpu)
        else:
            container_maxcpu.value = request.form.get("container_maxcpu")

        db.session.commit()

        container_manager.settings = settings_to_dict(ContainerSettingsModel.query.all())
        if container_manager.settings.get("docker_base_url") is not None:
            try:
                container_manager.initialize_connection(container_manager.settings, app)
            except ContainerException as err:
                flash(str(err), "error")
                return redirect(url_for(".route_containers_settings"))

        return redirect(url_for(".route_containers_dashboard"))

    @containers_bp.route('/dashboard', methods=['GET'])
    @admins_only
    def route_containers_dashboard():
        running_containers = ContainerInfoModel.query.order_by(ContainerInfoModel.timestamp.desc()).all()

        connected = False
        try:
            connected = container_manager.is_connected()
        except ContainerException:
            pass

        for i, container in enumerate(running_containers):
            try:
                running_containers[i].is_running = container_manager.is_container_running(container.container_id)
            except ContainerException:
                running_containers[i].is_running = False

        return render_template('container_dashboard.html', containers=running_containers, connected=connected)

    @containers_bp.route('/settings', methods=['GET'])
    @admins_only
    def route_containers_settings():
        running_containers = ContainerInfoModel.query.order_by(ContainerInfoModel.timestamp.desc()).all()
        return render_template('container_settings.html', settings=container_manager.settings)

    app.register_blueprint(containers_bp)
