const API_BASE = "http://127.0.0.1:5000";

window.onload = function () {

    if (localStorage.getItem("isLogin") === "true") {
        location.href = "index.html";
    }

};

document
    .getElementById("registerBtn")
    .addEventListener("click", register);

document.addEventListener("keydown", function (e) {

    if (e.key === "Enter") {
        register();
    }

});

async function register() {

    const username = document
        .getElementById("username")
        .value
        .trim();

    const password = document
        .getElementById("password")
        .value
        .trim();

    const confirmPassword = document
        .getElementById("confirmPassword")
        .value
        .trim();

    if (!username) {
        alert("请输入用户名");
        return;
    }

    if (password.length < 6) {
        alert("密码不少于6位");
        return;
    }

    if (password !== confirmPassword) {
        alert("两次密码不一致");
        return;
    }

    try {

        const response = await fetch(API_BASE + "/api/register", {

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

        alert(result.msg);

        if (result.code === 200) {
            // 注册成功自动登录，存储 token
            localStorage.setItem("isLogin", "true");
            localStorage.setItem("currentUser", username);
            localStorage.setItem("authToken", result.data.token);

            location.href = "index.html";

        }

    } catch (e) {

        alert("服务器连接失败");

        console.error(e);

    }

}