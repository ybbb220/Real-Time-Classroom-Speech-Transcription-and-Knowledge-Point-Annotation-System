const API_BASE = "http://127.0.0.1:5000";

window.onload = function () {

    if (localStorage.getItem("isLogin") === "true") {

        location.href = "index.html";

    }

    const remember = localStorage.getItem("rememberUser");

    if (remember) {

        document.getElementById("username").value = remember;

        document.getElementById("remember").checked = true;

    }

};

document
    .getElementById("loginBtn")
    .addEventListener("click", login);

document.addEventListener("keydown", function (e) {

    if (e.key === "Enter") {

        login();

    }

});

async function login() {

    const username = document
        .getElementById("username")
        .value
        .trim();

    const password = document
        .getElementById("password")
        .value
        .trim();

    const remember = document
        .getElementById("remember")
        .checked;

    if (!username) {

        alert("请输入用户名");

        return;

    }

    if (!password) {

        alert("请输入密码");

        return;

    }

    try {

        const response = await fetch(API_BASE + "/api/login", {

            method: "POST",

            headers: {

                "Content-Type": "application/json"

            },

            body: JSON.stringify({

                username,

                password

            })

        });

        const result = await response.json();

        if (result.code === 200) {

            localStorage.setItem("isLogin", "true");

            localStorage.setItem("currentUser", username);

            localStorage.setItem("authToken", result.data.token);

            if (remember) {

                localStorage.setItem("rememberUser", username);

            } else {

                localStorage.removeItem("rememberUser");

            }

            alert("登录成功");

            location.href = "index.html";

        } else {

            alert(result.msg);

        }

    } catch (e) {

        alert("服务器连接失败");

        console.error(e);

    }

}