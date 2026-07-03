document.addEventListener("DOMContentLoaded", () => {
    const API_ROUTES = "/api/routes";
    const API_SETTINGS = "/api/settings";
    const API_LOGS = "/api/logs";

    // DOM Elements
    const addRouteForm = document.getElementById("add-route-form");
    const settingsForm = document.getElementById("settings-form");
    const monitorsList = document.getElementById("monitors-list");
    const routeCountBadge = document.getElementById("route-count");
    const logsContainer = document.getElementById("logs-container");
    const clearLogsBtn = document.getElementById("clear-logs-btn");
    const refreshLogsBtn = document.getElementById("refresh-logs-btn");

    // Modal elements
    const routeModal = document.getElementById("route-modal");
    const closeModalBtn = document.getElementById("close-modal-btn");
    const modalDepCity = document.getElementById("modal-dep-city");
    const modalArrCity = document.getElementById("modal-arr-city");
    const modalDate = document.getElementById("modal-date");
    const modalTargetPrice = document.getElementById("modal-target-price");
    const flightsTableBody = document.getElementById("flights-table-body");
    const crawlerScreenshot = document.getElementById("crawler-screenshot");

    // Tab elements
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");

    // State Variables
    let currentChart = null;
    let currentModalRouteId = null;

    // Set default date in form to tomorrow
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dateInput = document.getElementById("date-input");
    dateInput.value = tomorrow.toISOString().split("T")[0];
    dateInput.min = new Date().toISOString().split("T")[0];

    // Notification Settings Elements
    const wechatTypeSelect = document.getElementById("wechat-type");
    const wechatKeyInput = document.getElementById("wechat-key");
    const keyGroup = document.getElementById("key-group");
    const keyLabel = document.getElementById("key-label");

    // Update settings form label based on type
    wechatTypeSelect.addEventListener("change", () => {
        const type = wechatTypeSelect.value;
        if (type === "none") {
            keyGroup.style.display = "none";
        } else {
            keyGroup.style.display = "block";
            if (type === "serverchan") {
                keyLabel.textContent = "Server酱 SendKey";
                wechatKeyInput.placeholder = "请输入 SCTKEY...";
            } else if (type === "pushdeer") {
                keyLabel.textContent = "PushDeer PushKey";
                wechatKeyInput.placeholder = "请输入 PKEY...";
            } else if (type === "bark") {
                keyLabel.textContent = "Bark Key";
                wechatKeyInput.placeholder = "请输入 Bark Device Key...";
            }
        }
    });

    // ----------------------------------------------------
    // Load & Render Routes
    // ----------------------------------------------------
    async function loadRoutes() {
        try {
            const res = await fetch(API_ROUTES);
            if (!res.ok) throw new Error("Failed to fetch routes");
            const routes = await res.json();
            renderRoutes(routes);
        } catch (err) {
            console.error(err);
            monitorsList.innerHTML = `
                <div class="no-monitors">
                    <i class="fa-solid fa-triangle-exclamation"></i>
                    <p>获取航班监控数据失败，请检查服务连接。</p>
                </div>
            `;
        }
    }

    function renderRoutes(routes) {
        routeCountBadge.textContent = `${routes.length} 条监控中`;
        
        if (routes.length === 0) {
            monitorsList.innerHTML = `
                <div class="no-monitors">
                    <i class="fa-solid fa-route"></i>
                    <p>暂无监控航线，请在左侧表单中添加。</p>
                </div>
            `;
            return;
        }

        monitorsList.innerHTML = "";
        routes.forEach(route => {
            const card = document.createElement("div");
            
            let alertFiredClass = "";
            if (route.target_price && route.latest_price && route.latest_price <= route.target_price) {
                alertFiredClass = "alert-fired";
            }
            
            const activeClass = route.is_active ? "active" : "";
            card.className = `monitor-card glass ${activeClass} ${alertFiredClass}`;
            
            const priceText = route.latest_price 
                ? `<span class="current-price ${alertFiredClass ? 'success' : ''}">¥${route.latest_price}</span>` 
                : `<span class="no-price">暂无数据</span>`;
                
            const targetText = route.target_price 
                ? `目标价: <span class="target-val">¥${route.target_price}</span>` 
                : `目标价: <span class="target-val">未设置</span>`;
                
            const formattedDate = route.date;
            
            card.innerHTML = `
                <div class="card-top">
                    <div class="route-badge">
                        <span>${route.departure}</span>
                        <i class="fa-solid fa-right-long"></i>
                        <span>${route.arrival}</span>
                    </div>
                    <div class="card-actions">
                        <button class="icon-btn trigger-btn" data-id="${route.id}" title="立即抓取">
                            <i class="fa-solid fa-rotate"></i>
                        </button>
                        <button class="icon-btn danger delete-btn" data-id="${route.id}" title="删除">
                            <i class="fa-solid fa-trash-can"></i>
                        </button>
                    </div>
                </div>
                <div class="card-middle">
                    <div class="date-info">
                        <i class="fa-solid fa-calendar-day"></i>
                        <span>${formattedDate}</span>
                    </div>
                    <div class="price-display">
                        ${priceText}
                        <div class="target-price-info">${targetText}</div>
                    </div>
                </div>
                <div class="card-bottom">
                    <div class="update-time">
                        <i class="fa-solid fa-clock-rotate-left"></i>
                        <span>${route.latest_checked_at ? formatRelativeTime(route.latest_checked_at) : '等待第一次检查'}</span>
                    </div>
                    <div class="status-toggle" data-id="${route.id}">
                        <span>${route.is_active ? '正在运行' : '已暂停'}</span>
                        <button class="icon-btn toggle-state-btn" title="${route.is_active ? '暂停' : '启动'}">
                            <i class="fa-solid ${route.is_active ? 'fa-pause' : 'fa-play'}"></i>
                        </button>
                    </div>
                </div>
            `;

            // Card click events - ignore click if triggered on buttons
            card.addEventListener("click", (e) => {
                if (e.target.closest(".icon-btn") || e.target.closest(".toggle-state-btn") || e.target.closest(".status-toggle")) {
                    return;
                }
                openModal(route.id);
            });

            // Action buttons events
            const triggerBtn = card.querySelector(".trigger-btn");
            triggerBtn.addEventListener("click", async (e) => {
                e.stopPropagation();
                const icon = triggerBtn.querySelector("i");
                icon.className = "fa-solid fa-spinner fa-spin";
                triggerBtn.disabled = true;
                await triggerRoute(route.id);
                // Refresh routes after 5 seconds for mobile layout scrolling
                setTimeout(loadRoutes, 5000);
            });

            const deleteBtn = card.querySelector(".delete-btn");
            deleteBtn.addEventListener("click", async (e) => {
                e.stopPropagation();
                if (confirm(`确定要删除 ${route.departure} -> ${route.arrival} 的监控吗？`)) {
                    await deleteRoute(route.id);
                }
            });

            const toggleBtn = card.querySelector(".toggle-state-btn");
            toggleBtn.addEventListener("click", async (e) => {
                e.stopPropagation();
                await toggleRouteState(route.id, !route.is_active);
            });

            monitorsList.appendChild(card);
        });
    }

    // ----------------------------------------------------
    // Operations
    // ----------------------------------------------------
    async function triggerRoute(routeId) {
        try {
            const res = await fetch(`${API_ROUTES}/${routeId}/trigger`, { method: "POST" });
            if (!res.ok) throw new Error("Failed to trigger update");
            addTempLog("INFO", `手动触发了手机APP监控 ID ${routeId} 运行`);
        } catch (err) {
            console.error(err);
            alert("启动手机爬虫失败，请检查连线。");
        }
    }

    async function deleteRoute(routeId) {
        try {
            const res = await fetch(`${API_ROUTES}/${routeId}`, { method: "DELETE" });
            if (!res.ok) throw new Error("Failed to delete route");
            loadRoutes();
            loadLogs();
        } catch (err) {
            console.error(err);
            alert("删除监控航线失败。");
        }
    }

    async function toggleRouteState(routeId, isActive) {
        try {
            const res = await fetch(`${API_ROUTES}/${routeId}/toggle`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ is_active: isActive })
            });
            if (!res.ok) throw new Error("Failed to toggle route state");
            loadRoutes();
            loadLogs();
        } catch (err) {
            console.error(err);
        }
    }

    // Add Route Form Submission
    addRouteForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const dep = document.getElementById("dep-input").value;
        const arr = document.getElementById("arr-input").value;
        const date = document.getElementById("date-input").value;
        const targetStr = document.getElementById("target-input").value;
        const interval = parseInt(document.getElementById("interval-input").value);

        const target_price = targetStr ? parseFloat(targetStr) : null;

        try {
            const res = await fetch(API_ROUTES, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    departure: dep,
                    arrival: arr,
                    date: date,
                    target_price: target_price,
                    interval_minutes: interval
                })
            });

            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || "添加失败");
            }

            // Clear inputs except defaults
            document.getElementById("dep-input").value = "";
            document.getElementById("arr-input").value = "";
            document.getElementById("target-input").value = "";
            
            loadRoutes();
            loadLogs();
            addTempLog("SYSTEM", "已添加监控任务。后台将自动连接手机APP抓取...");
        } catch (err) {
            console.error(err);
            alert(`添加失败: ${err.message}`);
        }
    });

    // ----------------------------------------------------
    // Settings Settings
    // ----------------------------------------------------
    async function loadSettings() {
        try {
            const res = await fetch(API_SETTINGS);
            if (!res.ok) throw new Error("Failed to load settings");
            const settings = await res.json();
            
            wechatTypeSelect.value = settings.wechat_type || "none";
            wechatKeyInput.value = settings.wechat_key || "";
            wechatTypeSelect.dispatchEvent(new Event("change"));
        } catch (err) {
            console.error("Error loading settings:", err);
        }
    }

    settingsForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const type = wechatTypeSelect.value;
        const key = wechatKeyInput.value;

        try {
            const res = await fetch(API_SETTINGS, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    wechat_type: type,
                    wechat_key: key
                })
            });

            if (!res.ok) throw new Error("Failed to update settings");
            alert("微信通知密钥保存成功！");
            loadLogs();
        } catch (err) {
            console.error(err);
            alert("保存通知配置失败。");
        }
    });

    // ----------------------------------------------------
    // Logs Panel
    // ----------------------------------------------------
    async function loadLogs() {
        try {
            const res = await fetch(API_LOGS);
            if (!res.ok) throw new Error("Failed to load logs");
            const logs = await res.json();
            renderLogs(logs);
        } catch (err) {
            console.error("Error loading logs:", err);
        }
    }

    function renderLogs(logs) {
        logsContainer.innerHTML = "";
        if (logs.length === 0) {
            logsContainer.innerHTML = `<div class="log-entry" style="color: var(--text-muted)">暂无运行日志</div>`;
            return;
        }

        logs.forEach(log => {
            const entry = document.createElement("div");
            entry.className = "log-entry";
            entry.innerHTML = `
                <span class="log-time">${log.timestamp.split(" ")[1]}</span>
                <span class="log-level ${log.level}">${log.level}</span>
                <span class="log-message">${escapeHtml(log.message)}</span>
            `;
            logsContainer.appendChild(entry);
        });
    }

    function addTempLog(level, message) {
        const entry = document.createElement("div");
        entry.className = "log-entry";
        const now = new Date().toLocaleTimeString();
        entry.innerHTML = `
            <span class="log-time">${now}</span>
            <span class="log-level ${level}">${level}</span>
            <span class="log-message">${escapeHtml(message)}</span>
        `;
        logsContainer.insertBefore(entry, logsContainer.firstChild);
    }

    clearLogsBtn.addEventListener("click", async () => {
        if (confirm("确定要清空手机监控日志吗？")) {
            try {
                await fetch(`${API_LOGS}/clear`, { method: "POST" });
                loadLogs();
            } catch (err) {
                console.error(err);
            }
        }
    });

    refreshLogsBtn.addEventListener("click", () => {
        loadLogs();
    });

    // ----------------------------------------------------
    // Modal & Details View
    // ----------------------------------------------------
    async function openModal(routeId) {
        currentModalRouteId = routeId;
        routeModal.style.display = "flex";
        
        tabBtns.forEach(btn => btn.classList.remove("active"));
        tabContents.forEach(content => content.classList.remove("active"));
        tabBtns[0].classList.add("active");
        document.getElementById("tab-chart").classList.add("active");

        crawlerScreenshot.src = routeScreenshotSrc(routeId);

        try {
            const res = await fetch(`${API_ROUTES}/${routeId}/history`);
            if (!res.ok) throw new Error("Failed to load details");
            const data = await res.json();
            
            modalDepCity.textContent = data.route.departure;
            modalArrCity.textContent = data.route.arrival;
            modalDate.textContent = data.route.date;
            modalTargetPrice.textContent = data.route.target_price ? `¥${data.route.target_price}` : "未设置";

            renderFlightsTable(data.flights);
            renderChart(data.trend);

        } catch (err) {
            console.error(err);
            alert("加载详情数据失败。");
        }
    }

    function renderFlightsTable(flights) {
        flightsTableBody.innerHTML = "";
        
        if (flights.length === 0) {
            flightsTableBody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 30px;">
                        <i class="fa-solid fa-triangle-exclamation" style="margin-right: 6px;"></i> 暂无手机App获取的航班数据，请等待第一次自动化完成。
                    </td>
                </tr>
            `;
            return;
        }

        const latestCheckTime = flights[flights.length - 1].checked_at;
        const currentFlights = flights.filter(f => f.checked_at === latestCheckTime);
        currentFlights.sort((a, b) => a.price - b.price);

        currentFlights.forEach(f => {
            const tr = document.createElement("tr");
            const depTime = f.departure_time ? f.departure_time.split(" ")[1] || f.departure_time : "未知";
            const arrTime = f.arrival_time ? f.arrival_time.split(" ")[1] || f.arrival_time : "未知";
            
            tr.innerHTML = `
                <td><i class="fa-solid fa-plane" style="margin-right: 8px; color: var(--primary)"></i>${f.airline}</td>
                <td><strong>${f.flight_number}</strong></td>
                <td>${depTime}</td>
                <td>${arrTime}</td>
                <td><span class="price-val">¥${f.price}</span></td>
                <td><span class="badge ${f.is_transfer ? 'warning' : 'info'}">${f.is_transfer ? '转机' : '直飞'}</span></td>
                <td><span class="badge ${f.transit_visa && f.transit_visa !== '不需要' ? 'danger' : 'success'}">${f.transit_visa || '免签/无需'}</span></td>
                <td>
                    ${f.screenshot_path ? `<a href="${f.screenshot_path}" target="_blank" class="screenshot-link" title="点击查看详情截图"><i class="fa-solid fa-image"></i> 查看</a>` : `<span style="color:var(--text-muted); font-size: 0.9em;">-</span>`}
                </td>
            `;
            flightsTableBody.appendChild(tr);
        });
    }

    function renderChart(trendData) {
        const ctx = document.getElementById("priceChart").getContext("2d");
        
        if (currentChart) {
            currentChart.destroy();
        }

        if (trendData.length === 0) {
            ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
            return;
        }

        const labels = trendData.map(d => d.checked_at.split(" ")[1] || d.checked_at);
        const prices = trendData.map(d => d.lowest_price);

        const gradient = ctx.createLinearGradient(0, 0, 0, 300);
        gradient.addColorStop(0, "rgba(58, 134, 255, 0.4)");
        gradient.addColorStop(1, "rgba(131, 56, 236, 0.0)");

        currentChart = new Chart(ctx, {
            type: "line",
            data: {
                labels: labels,
                datasets: [{
                    label: "最低票价 (元)",
                    data: prices,
                    borderColor: "#3a86ff",
                    borderWidth: 3,
                    pointBackgroundColor: "#8338ec",
                    pointBorderColor: "#fff",
                    pointHoverRadius: 7,
                    tension: 0.35,
                    fill: true,
                    backgroundColor: gradient
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        mode: "index",
                        intersect: false,
                        padding: 12,
                        backgroundColor: "rgba(15, 17, 28, 0.95)",
                        titleFont: { family: "Outfit", size: 13 },
                        bodyFont: { family: "Outfit", size: 14, weight: "bold" },
                        borderColor: "rgba(255,255,255,0.1)",
                        borderWidth: 1
                    }
                },
                scales: {
                    x: {
                        grid: { color: "rgba(255, 255, 255, 0.05)" },
                        ticks: { color: "#9ca3af", font: { family: "Outfit" } }
                    },
                    y: {
                        grid: { color: "rgba(255, 255, 255, 0.05)" },
                        ticks: { color: "#9ca3af", font: { family: "Outfit" } }
                    }
                }
            }
        });
    }

    // Modal Close
    closeModalBtn.addEventListener("click", () => {
        routeModal.style.display = "none";
        currentModalRouteId = null;
    });

    window.addEventListener("click", (e) => {
        if (e.target === routeModal) {
            routeModal.style.display = "none";
            currentModalRouteId = null;
        }
    });

    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            const targetTab = btn.getAttribute("data-tab");
            
            tabBtns.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            
            btn.classList.add("active");
            document.getElementById(targetTab).classList.add("active");
        });
    });

    // ----------------------------------------------------
    // Helpers
    // ----------------------------------------------------
    function escapeHtml(text) {
        return text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function formatRelativeTime(dateTimeStr) {
        try {
            const parts = dateTimeStr.split(/[- :]/);
            const date = new Date(parts[0], parts[1]-1, parts[2], parts[3], parts[4], parts[5]);
            const now = new Date();
            const diffSeconds = Math.floor((now - date) / 1000);
            
            if (diffSeconds < 60) return "刚刚更新";
            const diffMinutes = Math.floor(diffSeconds / 60);
            if (diffMinutes < 60) return `${diffMinutes} 分钟前`;
            const diffHours = Math.floor(diffMinutes / 60);
            if (diffHours < 24) return `${diffHours} 小时前`;
            return dateTimeStr.split(" ")[0];
        } catch (e) {
            return dateTimeStr;
        }
    }

    function routeScreenshotSrc(routeId) {
        return `/static/screenshot_route_${routeId}.png?t=${new Date().getTime()}`;
    }

    // ----------------------------------------------------
    // Auto Loops & Initialization
    // ----------------------------------------------------
    loadRoutes();
    loadSettings();
    loadLogs();

    setInterval(() => {
        loadLogs();
        if (routeModal.style.display === "flex" && currentModalRouteId) {
            crawlerScreenshot.src = routeScreenshotSrc(currentModalRouteId);
            fetch(`${API_ROUTES}/${currentModalRouteId}/history`)
                .then(res => {
                    if (res.ok) return res.json();
                })
                .then(data => {
                    if (data) {
                        renderFlightsTable(data.flights);
                        renderChart(data.trend);
                    }
                })
                .catch(err => console.error("Modal quiet refresh error:", err));
        }
    }, 5000);

    setInterval(loadRoutes, 30000);
});
