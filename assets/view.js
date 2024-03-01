CTFd._internal.challenge.data = undefined;

CTFd._internal.challenge.renderer = null;

CTFd._internal.challenge.preRender = function () {};

CTFd._internal.challenge.render = function (markdown) {
	return CTFd._internal.challenge.renderer.render(markdown);
};

CTFd._internal.challenge.postRender = function () {};

CTFd._internal.challenge.submit = function (preview) {
	var challenge_id = parseInt(CTFd.lib.$("#challenge-id").val());
	var submission = CTFd.lib.$("#challenge-input").val();

	var body = {
		challenge_id: challenge_id,
		submission: submission,
	};
	var params = {};
	if (preview) {
		params["preview"] = true;
	}

	return CTFd.api
		.post_challenge_attempt(params, body)
		.then(function (response) {
			if (response.status === 429) {
				// User was ratelimited but process response
				return response;
			}
			if (response.status === 403) {
				// User is not logged in or CTF is paused.
				return response;
			}
			return response;
		});
};

function mergeQueryParams(parameters, queryParameters) {
	if (parameters.$queryParameters) {
		Object.keys(parameters.$queryParameters).forEach(function (
			parameterName
		) {
			var parameter = parameters.$queryParameters[parameterName];
			queryParameters[parameterName] = parameter;
		});
	}

	return queryParameters;
}

var timerId;
function resetTimer() {
	var containerExpires = document.getElementById("container-expires");
	var containerExpiresTime = document.getElementById("container-expires-time");

	clearInterval(timerId);
	containerExpires.innerHTML = "";
	containerExpiresTime.innerHTML = "";
}

function startTimer(expires) {
	resetTimer();
	var requestButton = document.getElementById("container-request-btn");
	var stopButton = document.getElementById("container-stop-btn");
	var requestResult = document.getElementById("container-request-result");
	var requestError = document.getElementById("container-request-error");

	var containerExpires = document.getElementById("container-expires");
	var containerExpiresTime = document.getElementById("container-expires-time");
	var now = new Date().getTime();
	var distance = expires * 1000 - now;

	var expirationTime = new Date(now + distance);
	containerExpires.innerHTML = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60)) + " minutes";
	containerExpiresTime.innerHTML = expirationTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

	timerId = setInterval(function() {
		now = new Date().getTime();
		distance = expires * 1000 - now;

		if (distance <= 0) {
			clearInterval(timerId);

			requestError.style.display = "none";
			requestResult.style.display = "none";
			requestButton.style.display = "";
			requestButton.removeAttribute("disabled");
			stopButton.removeAttribute("disabled");
		} else {
			var minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
			var seconds = Math.floor((distance % (1000 * 60)) / 1000);

			if (minutes === 0) {
				containerExpires.innerHTML = seconds + " second" + (seconds > 1 ? "s" : "");
			} else {
				containerExpires.innerHTML = minutes + " minute" + (minutes > 1 ? "s" : "");
			}
		}
	}, 1000);
}

function containerRequest(challenge_id) {
	var path = "/containers/api/request";
	var requestButton = document.getElementById("container-request-btn");
	var requestResult = document.getElementById("container-request-result");
	var connectionInfo = document.getElementById("container-connection-info");
	var requestError = document.getElementById("container-request-error");

	requestButton.setAttribute("disabled", "disabled");

	var xhr = new XMLHttpRequest();
	xhr.open("POST", path, true);
	xhr.setRequestHeader("Content-Type", "application/json");
	xhr.setRequestHeader("Accept", "application/json");
	xhr.setRequestHeader("CSRF-Token", init.csrfNonce);
	xhr.send(JSON.stringify({ chal_id: challenge_id }));
	xhr.onload = function () {
		var data = JSON.parse(this.responseText);
		if (data.error !== undefined) {
			requestError.style.display = "";
			requestError.firstElementChild.innerHTML = data.error;
			requestButton.removeAttribute("disabled");
		} else if (data.message !== undefined) {
			requestError.style.display = "";
			requestError.firstElementChild.innerHTML = data.message;
			requestButton.removeAttribute("disabled");
		} else {
			requestError.style.display = "none";
			requestError.firstElementChild.innerHTML = "";
			requestButton.style.display = "none";
			if (data.connection.startsWith("http")) {
				connectionInfo.innerHTML = `<a href="${data.connection}" target="_blank">${data.connection}</a>`;
			} else {
				connectionInfo.innerHTML = data.connection;
			}
			startTimer(data.expires);
			requestResult.style.display = "";
		}
	};
}

function containerReset(challenge_id) {
	var path = "/containers/api/reset";
	var resetButton = document.getElementById("container-reset-btn");
	var requestResult = document.getElementById("container-request-result");
	var connectionInfo = document.getElementById("container-connection-info");
	var requestError = document.getElementById("container-request-error");

	resetButton.setAttribute("disabled", "disabled");

	var xhr = new XMLHttpRequest();
	xhr.open("POST", path, true);
	xhr.setRequestHeader("Content-Type", "application/json");
	xhr.setRequestHeader("Accept", "application/json");
	xhr.setRequestHeader("CSRF-Token", init.csrfNonce);
	xhr.send(JSON.stringify({ chal_id: challenge_id }));
	xhr.onload = function () {
		var data = JSON.parse(this.responseText);
		if (data.error !== undefined) {
			requestError.style.display = "";
			requestError.firstElementChild.innerHTML = data.error;
			resetButton.removeAttribute("disabled");
		} else if (data.message !== undefined) {
			requestError.style.display = "";
			requestError.firstElementChild.innerHTML = data.message;
			resetButton.removeAttribute("disabled");
		} else {
			requestError.style.display = "none";
			if (data.connection.startsWith("http")) {
				connectionInfo.innerHTML = `<a href="${data.connection}" target="_blank">${data.connection}</a>`;
			} else {
				connectionInfo.innerHTML = data.connection;
			}
			startTimer(data.expires);
			requestResult.style.display = "";
			resetButton.removeAttribute("disabled");
		}
	};
}

function containerRenew(challenge_id) {
	var path = "/containers/api/renew";
	var renewButton = document.getElementById("container-renew-btn");
	var requestResult = document.getElementById("container-request-result");
	var requestError = document.getElementById("container-request-error");

	renewButton.setAttribute("disabled", "disabled");

	var xhr = new XMLHttpRequest();
	xhr.open("POST", path, true);
	xhr.setRequestHeader("Content-Type", "application/json");
	xhr.setRequestHeader("Accept", "application/json");
	xhr.setRequestHeader("CSRF-Token", init.csrfNonce);
	xhr.send(JSON.stringify({ chal_id: challenge_id }));
	xhr.onload = function () {
		var data = JSON.parse(this.responseText);
		if (data.error !== undefined) {
			requestError.style.display = "";
			requestError.firstElementChild.innerHTML = data.error;
			renewButton.removeAttribute("disabled");
		} else if (data.message !== undefined) {
			requestError.style.display = "";
			requestError.firstElementChild.innerHTML = data.message;
			renewButton.removeAttribute("disabled");
		} else {
			requestError.style.display = "none";
			requestResult.style.display = "";
			startTimer(data.expires);
			renewButton.removeAttribute("disabled");
		}
	};
}

function containerStop(challenge_id) {
	var path = "/containers/api/stop";
	var requestButton = document.getElementById("container-request-btn");
	var stopButton = document.getElementById("container-stop-btn");
	var requestResult = document.getElementById("container-request-result");
	var requestError = document.getElementById("container-request-error");

	stopButton.setAttribute("disabled", "disabled");

	var xhr = new XMLHttpRequest();
	xhr.open("POST", path, true);
	xhr.setRequestHeader("Content-Type", "application/json");
	xhr.setRequestHeader("Accept", "application/json");
	xhr.setRequestHeader("CSRF-Token", init.csrfNonce);
	xhr.send(JSON.stringify({ chal_id: challenge_id }));
	xhr.onload = function () {
		var data = JSON.parse(this.responseText);
		if (data.error !== undefined) {
			requestError.style.display = "";
			requestError.firstElementChild.innerHTML = data.error;
			stopButton.removeAttribute("disabled");
		} else if (data.message !== undefined) {
			requestError.style.display = "";
			requestError.firstElementChild.innerHTML = data.message;
			stopButton.removeAttribute("disabled");
		} else {
			requestError.style.display = "none";
			requestResult.style.display = "none";
			requestButton.style.display = "";
			resetTimer();
			requestButton.removeAttribute("disabled");
			stopButton.removeAttribute("disabled");
		}
	};
}
