const API_BASE = "http://127.0.0.1:5000";

function getAuthHeaders() {
    const token = localStorage.getItem("authToken") || "";
    return {
        "Authorization": "Bearer " + token,
    };
}

// 页面加载
window.onload = function () {
    checkLogin();
    loadCurrentUser();
    initMenu();
    initUpload();
    initButtons();
};


function checkLogin() {
    const isLogin = localStorage.getItem("isLogin");
    if (isLogin !== "true") {
        alert("请先登录！");
        window.location.href = "login.html";
    }
}


function loadCurrentUser() {
    const username = localStorage.getItem("currentUser") || "用户";
    document.getElementById("currentUser").innerText = username;
}

function initMenu() {
    const menus = document.querySelectorAll(".sidebar li");
    const pages = document.querySelectorAll(".page");
    menus.forEach(menu => {
        menu.addEventListener("click", function () {
            menus.forEach(item => item.classList.remove("active"));
            this.classList.add("active");
            const page = this.dataset.page;
            pages.forEach(p => p.classList.remove("active-page"));
            document.getElementById(page).classList.add("active-page");

            // 切换到知识点页面时自动加载知识库
            if (page === "knowledge") {
                loadKnowledgeBase();
            }
        });
    });
}


function initButtons() {
    // 退出登录
    document.getElementById("logoutBtn").addEventListener("click", logout);

    // 上传并转写
    document.getElementById("startBtn").addEventListener("click", uploadAndTranscribe);

    // 清空结果
    document.getElementById("stopBtn").addEventListener("click", clearResults);

    // 知识库 — 添加
    document.getElementById("kbAddBtn").addEventListener("click", addKnowledgeItem);

    // 知识库 — 回车添加
    document.getElementById("kbInput").addEventListener("keydown", function (e) {
        if (e.key === "Enter") addKnowledgeItem();
    });
}


async function logout() {
    if (!confirm("确定退出登录吗？")) return;

    // 通知后端使 token 失效
    try {
        await fetch(API_BASE + "/api/logout", {
            method: "POST",
            headers: getAuthHeaders(),
        });
    } catch (e) {
        // 即使后端不可达也要完成本地登出
    }

    localStorage.removeItem("isLogin");
    localStorage.removeItem("currentUser");
    localStorage.removeItem("authToken");
    alert("已退出登录");
    window.location.href = "login.html";
}

let selectedFile = null;

function initUpload() {
    const uploadArea = document.getElementById("uploadArea");
    const fileInput = document.getElementById("audioFileInput");
    const startBtn = document.getElementById("startBtn");

    // 点击上传区域 → 触发文件选择
    uploadArea.addEventListener("click", function () {
        fileInput.click();
    });

    // 文件选择
    fileInput.addEventListener("change", function () {
        if (fileInput.files.length > 0) {
            selectedFile = fileInput.files[0];
            // 显示已选文件
            uploadArea.querySelector("p:first-of-type").textContent =
                "已选择：" + selectedFile.name;
            uploadArea.classList.add("has-file");
            startBtn.disabled = false;
            startBtn.textContent = "上传并转写";
        }
    });

    // 拖拽支持
    uploadArea.addEventListener("dragover", function (e) {
        e.preventDefault();
        uploadArea.classList.add("dragover");
    });
    uploadArea.addEventListener("dragleave", function () {
        uploadArea.classList.remove("dragover");
    });
    uploadArea.addEventListener("drop", function (e) {
        e.preventDefault();
        uploadArea.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            fileInput.dispatchEvent(new Event("change"));
        }
    });
}

async function uploadAndTranscribe() {
    if (!selectedFile) {
        alert("请先选择音频文件");
        return;
    }

    const startBtn = document.getElementById("startBtn");
    const statusDiv = document.getElementById("uploadStatus");
    const speechDiv = document.getElementById("speechText");

    // 禁用按钮，显示进度
    startBtn.disabled = true;
    startBtn.textContent = "转写中…";
    statusDiv.classList.remove("hidden");
    statusDiv.textContent = "⏳ 正在上传并转写，实时显示中…";
    statusDiv.className = "upload-status uploading";
    speechDiv.innerHTML = "";

    // 清空之前的知识点匹配
    document.getElementById("matchList").innerHTML =
        '<li style="color:#999;">等待转写结果…</li>';

    const formData = new FormData();
    formData.append("audio", selectedFile);

    // 超时控制
    const controller = new AbortController();
    const timeoutId = setTimeout(function () {
        controller.abort();
    }, 6 * 60 * 1000);

    try {
        const response = await fetch(API_BASE + "/api/asr/stream", {
            method: "POST",
            headers: getAuthHeaders(),
            body: formData,
            signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
            const rawText = await response.text();
            let errMsg = "HTTP " + response.status;
            try {
                const errJson = JSON.parse(rawText);
                errMsg = errJson.msg || errMsg;
            } catch (e) { /* ignore */ }
            statusDiv.textContent = "❌ " + errMsg;
            statusDiv.className = "upload-status error";
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";          // 跨 chunk 的行缓冲
        let sentenceCount = 0;    // 已收到的句子数
        let fullText = "";        // 累积全部文本
        let allKnowledge = [];    // 累积全部知识点匹配

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            // 解码并追加到缓冲
            buffer += decoder.decode(value, { stream: true });

            // 按行解析 NDJSON
            const lines = buffer.split("\n");
            // 最后一行可能不完整，保留到下次
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.trim()) continue;

                let event;
                try {
                    event = JSON.parse(line);
                } catch (e) {
                    console.warn("跳过无效 JSON 行:", line.slice(0, 80));
                    continue;
                }

                switch (event.type) {
                    case "start":
                        // 连接已建立，转写开始
                        statusDiv.textContent = "🎙️ 正在转写…（已识别 0 句）";
                        break;

                    case "sentence":
                        sentenceCount++;
                        fullText += event.text + "\n";
                        // 判断该句是否有 FAISS 匹配的知识点
                        const hasKnowledge = event.knowledge && event.knowledge.length > 0;
                        // 创建句子 span 元素
                        const sentenceSpan = document.createElement("span");
                        sentenceSpan.textContent = event.text + "\n";
                        if (hasKnowledge) {
                            sentenceSpan.className = "sentence-highlight";
                            sentenceSpan.title = event.knowledge
                                .map(function (k) { return k.doc + " (相似度: " + k.score.toFixed(2) + ")"; })
                                .join("\n");
                        }
                        speechDiv.appendChild(sentenceSpan);
                        // 自动滚到底部
                        speechDiv.scrollTop = speechDiv.scrollHeight;
                        // 状态显示当前进度
                        statusDiv.textContent =
                            "🎙️ 正在转写…（已识别 " + sentenceCount + " 句）";
                        // 收集知识点
                        if (hasKnowledge) {
                            event.knowledge.forEach(function (k) {
                                allKnowledge.push({
                                    text: event.text,
                                    doc: k.doc,
                                    score: k.score,
                                });
                            });
                            // 实时更新知识点匹配列表
                            renderMatchResults(allKnowledge);
                        }
                        break;

                    case "complete":
                        statusDiv.textContent =
                            "✅ 转写完成！共识别 " + event.sentence_count + " 句";
                        statusDiv.className = "upload-status success";
                        // 更新首页统计
                        updateDashboardStream(event);
                        // 下载知识点覆盖清单
                        if (allKnowledge.length > 0) {
                            exportKnowledgeDocx(allKnowledge);
                        }
                        // 自动跳转到知识点页面
                        setTimeout(function () {
                            document.querySelector(
                                '.sidebar li[data-page="knowledge"]'
                            ).click();
                        }, 500);
                        break;

                    case "error":
                        statusDiv.textContent = "❌ " + event.message;
                        statusDiv.className = "upload-status error";
                        break;
                }
            }
        }
    } catch (err) {
        clearTimeout(timeoutId);
        if (err.name === "AbortError") {
            statusDiv.textContent =
                "⏰ 转写超时（6分钟），请检查音频格式是否为 16kHz 单声道 16bit，以及 API 配置是否正确";
            statusDiv.className = "upload-status error";
        } else {
            statusDiv.textContent =
                "❌ 网络错误，请确认后端服务已启动: " + err.message;
            statusDiv.className = "upload-status error";
        }
    } finally {
        startBtn.disabled = false;
        startBtn.textContent = "上传并转写";
    }
}


function renderMatchResults(knowledgeItems) {
    const list = document.getElementById("matchList");
    list.innerHTML = "";

    if (knowledgeItems.length === 0) {
        const li = document.createElement("li");
        li.textContent = "（未匹配到相关知识点）";
        li.style.color = "#999";
        list.appendChild(li);
        return;
    }

    knowledgeItems.forEach(function (k) {
        const li = document.createElement("li");
        li.innerHTML =
            '<span class="k-source">📝 ' +
            escapeHtml(k.text) +
            "</span>" +
            '<span class="k-tag">🏷 ' +
            escapeHtml(k.doc) +
            " (相似度: " +
            k.score.toFixed(2) +
            ")</span>";
        list.appendChild(li);
    });

    // 更新首页知识点数量
    document.getElementById("knowledgeCount").textContent = knowledgeItems.length;
}


function updateDashboardStream(event) {
    const todayEl = document.getElementById("todayCount");
    const current = parseInt(todayEl.textContent) || 0;
    todayEl.textContent = current + 1;
}


function updateKnowledge(sentences) {
    const list = document.getElementById("matchList");
    list.innerHTML = "";

    let hasKnowledge = false;
    sentences.forEach(function (s) {
        if (s.knowledge && s.knowledge.length > 0) {
            hasKnowledge = true;
            s.knowledge.forEach(function (k) {
                const li = document.createElement("li");
                li.innerHTML =
                    '<span class="k-source">📝 ' +
                    escapeHtml(s.text) +
                    "</span>" +
                    '<span class="k-tag">🏷 ' +
                    escapeHtml(k.doc) +
                    " (相似度: " +
                    k.score.toFixed(2) +
                    ")</span>";
                list.appendChild(li);
            });
        }
    });

    if (!hasKnowledge) {
        const li = document.createElement("li");
        li.textContent = "（未匹配到相关知识点）";
        li.style.color = "#999";
        list.appendChild(li);
    }

    // 更新知识点数量
    document.getElementById("knowledgeCount").textContent =
        document.querySelectorAll("#matchList li").length;
}

function updateDashboard(data) {
    // 今日识别次数 +1
    const todayEl = document.getElementById("todayCount");
    const current = parseInt(todayEl.textContent) || 0;
    todayEl.textContent = current + 1;
}

function clearResults() {
    selectedFile = null;
    document.getElementById("speechText").innerHTML = "";
    document.getElementById("uploadStatus").classList.add("hidden");
    document.getElementById("startBtn").disabled = true;
    document.getElementById("audioFileInput").value = "";

    const uploadArea = document.getElementById("uploadArea");
    uploadArea.querySelector("p:first-of-type").textContent =
        "点击或拖拽上传音频文件";
    uploadArea.classList.remove("has-file");
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

async function exportKnowledgeDocx(knowledgeItems) {
    try {
        const response = await fetch(API_BASE + "/api/knowledge/export", {
            method: "POST",
            headers: Object.assign(
                { "Content-Type": "application/json" },
                getAuthHeaders()
            ),
            body: JSON.stringify({ items: knowledgeItems }),
        });

        if (!response.ok) {
            console.error("导出失败: HTTP " + response.status);
            return;
        }

        // 获取 blob 并触发下载
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "知识点覆盖清单.docx";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (err) {
        console.error("导出知识点清单失败:", err.message);
    }
}

async function loadKnowledgeBase() {
    const list = document.getElementById("kbList");
    list.innerHTML = '<li class="kb-empty">加载中…</li>';

    try {
        const resp = await fetch(API_BASE + "/api/knowledge", {
            headers: getAuthHeaders(),
        });
        const result = await resp.json();
        if (result.code === 200) {
            renderKnowledgeList(result.data);
        } else {
            list.innerHTML = '<li class="kb-empty" style="color:#ff4d4f;">加载失败: ' + escapeHtml(result.msg) + '</li>';
        }
    } catch (err) {
        list.innerHTML = '<li class="kb-empty" style="color:#ff4d4f;">网络错误: ' + escapeHtml(err.message) + '</li>';
    }
}

function renderKnowledgeList(items) {
    const list = document.getElementById("kbList");
    list.innerHTML = "";

    if (!items || items.length === 0) {
        const li = document.createElement("li");
        li.className = "kb-empty";
        li.textContent = "知识库为空，请添加知识点";
        list.appendChild(li);
        return;
    }

    items.forEach(function (item) {
        const li = document.createElement("li");
        li.className = "kb-item";
        li.innerHTML =
            '<span class="kb-content">' + escapeHtml(item.content) + '</span>' +
            '<span class="kb-time">' + escapeHtml(item.created_at) + '</span>' +
            '<div class="kb-actions">' +
            '<button class="kb-edit-btn" data-id="' + item.id + '">编辑</button>' +
            '<button class="kb-del-btn" data-id="' + item.id + '">删除</button>' +
            '</div>';

        // 编辑按钮事件
        li.querySelector(".kb-edit-btn").addEventListener("click", function () {
            const id = this.dataset.id;
            const oldContent = this.closest(".kb-item").querySelector(".kb-content").textContent;
            const newContent = prompt("编辑知识点内容：", oldContent);
            if (newContent !== null && newContent.trim() !== "" && newContent.trim() !== oldContent) {
                updateKnowledgeItem(id, newContent.trim());
            }
        });

        // 删除按钮事件
        li.querySelector(".kb-del-btn").addEventListener("click", function () {
            const id = this.dataset.id;
            if (confirm("确定要删除该知识点吗？")) {
                deleteKnowledgeItem(id);
            }
        });

        list.appendChild(li);
    });

    // 更新首页知识点数量
    document.getElementById("knowledgeCount").textContent = items.length;
}

async function addKnowledgeItem() {
    const input = document.getElementById("kbInput");
    const btn = document.getElementById("kbAddBtn");
    const content = input.value.trim();
    if (!content) {
        alert("请输入知识点内容");
        return;
    }

    btn.disabled = true;
    btn.textContent = "添加中…";

    try {
        const resp = await fetch(API_BASE + "/api/knowledge", {
            method: "POST",
            headers: Object.assign(
                { "Content-Type": "application/json" },
                getAuthHeaders()
            ),
            body: JSON.stringify({ content: content }),
        });
        const result = await resp.json();
        if (result.code === 200) {
            input.value = "";
            loadKnowledgeBase();
        } else {
            alert("添加失败: " + result.msg);
        }
    } catch (err) {
        alert("网络错误: " + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = "添加";
    }
}

async function updateKnowledgeItem(id, content) {
    try {
        const resp = await fetch(API_BASE + "/api/knowledge/" + id, {
            method: "PUT",
            headers: Object.assign(
                { "Content-Type": "application/json" },
                getAuthHeaders()
            ),
            body: JSON.stringify({ content: content }),
        });
        const result = await resp.json();
        if (result.code === 200) {
            loadKnowledgeBase();
        } else {
            alert("更新失败: " + result.msg);
        }
    } catch (err) {
        alert("网络错误: " + err.message);
    }
}

async function deleteKnowledgeItem(id) {
    try {
        const resp = await fetch(API_BASE + "/api/knowledge/" + id, {
            method: "DELETE",
            headers: getAuthHeaders(),
        });
        const result = await resp.json();
        if (result.code === 200) {
            loadKnowledgeBase();
        } else {
            alert("删除失败: " + result.msg);
        }
    } catch (err) {
        alert("网络错误: " + err.message);
    }
}
