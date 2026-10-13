"""High-Frequency Trading Terminal Dashboard HTML generator for ChronosMatch."""


def get_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ChronosMatch | Zero-Copy HFT Engine</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #080a0f;
            --bg-surface: #0f131c;
            --bg-elevated: #161b26;
            --border: #232a3b;
            --border-highlight: #333d54;
            --green: #10b981;
            --green-glow: rgba(16, 185, 129, 0.15);
            --red: #ef4444;
            --red-glow: rgba(239, 68, 68, 0.15);
            --blue: #3b82f6;
            --blue-glow: rgba(59, 130, 246, 0.15);
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: 'Space Grotesk', -apple-system, sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
        }

        .mono {
            font-family: 'JetBrains Mono', monospace;
        }

        header {
            background: var(--bg-surface);
            border-bottom: 1px solid var(--border);
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .logo-group {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .logo-badge {
            background: linear-gradient(135deg, #2563eb, #10b981);
            color: #fff;
            font-weight: 700;
            font-size: 14px;
            padding: 4px 10px;
            border-radius: 6px;
            letter-spacing: 1px;
        }

        .logo-title {
            font-size: 18px;
            font-weight: 700;
            letter-spacing: -0.5px;
        }

        .logo-tag {
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1.5px;
        }

        .header-stats {
            display: flex;
            align-items: center;
            gap: 24px;
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: var(--green);
            font-size: 12px;
            font-weight: 600;
            padding: 4px 12px;
            border-radius: 20px;
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            background: var(--green);
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        /* Metrics Bar */
        .metrics-bar {
            background: var(--bg-surface);
            border-bottom: 1px solid var(--border);
            padding: 10px 24px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
        }

        .metric-card {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }

        .metric-label {
            font-size: 11px;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .metric-val {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .metric-highlight {
            color: var(--green);
        }

        /* Main Workspace */
        main {
            flex: 1;
            padding: 20px 24px;
            display: grid;
            grid-template-columns: 340px 1fr 340px;
            gap: 20px;
        }

        @media (max-width: 1200px) {
            main {
                grid-template-columns: 1fr;
            }
        }

        .panel {
            background: var(--bg-surface);
            border: 1px solid var(--border);
            border-radius: 10px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .panel-header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
            background: var(--bg-elevated);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .panel-title {
            font-size: 13px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-secondary);
        }

        /* Symbols Switcher */
        .symbol-tabs {
            display: flex;
            gap: 6px;
        }

        .symbol-tab {
            background: transparent;
            border: 1px solid var(--border);
            color: var(--text-secondary);
            font-size: 11px;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.15s ease;
        }

        .symbol-tab.active, .symbol-tab:hover {
            background: var(--blue-glow);
            border-color: var(--blue);
            color: #fff;
        }

        /* Order Book Table */
        .book-container {
            display: flex;
            flex-direction: column;
            flex: 1;
            padding: 8px 12px;
            font-size: 12px;
        }

        .book-table-hdr {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            padding: 6px 4px;
            color: var(--text-muted);
            font-size: 11px;
            text-transform: uppercase;
            border-bottom: 1px solid var(--border);
        }

        .book-row {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            padding: 4px 4px;
            position: relative;
            font-size: 12px;
        }

        .book-row .bar {
            position: absolute;
            top: 1px;
            bottom: 1px;
            right: 0;
            z-index: 0;
            opacity: 0.18;
            border-radius: 2px;
        }

        .book-row.ask .bar {
            background: var(--red);
        }

        .book-row.bid .bar {
            background: var(--green);
        }

        .book-row span {
            position: relative;
            z-index: 1;
        }

        .ask-price {
            color: var(--red);
            font-weight: 600;
        }

        .bid-price {
            color: var(--green);
            font-weight: 600;
        }

        .spread-banner {
            margin: 10px 0;
            padding: 8px 12px;
            background: var(--bg-elevated);
            border: 1px dashed var(--border);
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
        }

        /* Order Form */
        .order-form {
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        .side-toggle {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }

        .side-btn {
            padding: 10px;
            border: 1px solid var(--border);
            background: var(--bg-elevated);
            color: var(--text-secondary);
            font-weight: 700;
            font-size: 13px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s ease;
        }

        .side-btn.buy.active {
            background: var(--green);
            border-color: var(--green);
            color: #fff;
            box-shadow: 0 0 14px var(--green-glow);
        }

        .side-btn.sell.active {
            background: var(--red);
            border-color: var(--red);
            color: #fff;
            box-shadow: 0 0 14px var(--red-glow);
        }

        .form-group {
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .form-label {
            font-size: 11px;
            text-transform: uppercase;
            color: var(--text-muted);
            letter-spacing: 0.5px;
        }

        .form-input, .form-select {
            background: var(--bg-elevated);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 9px 12px;
            border-radius: 6px;
            font-size: 13px;
            outline: none;
            transition: border-color 0.15s;
        }

        .form-input:focus, .form-select:focus {
            border-color: var(--blue);
        }

        .submit-btn {
            margin-top: 8px;
            background: linear-gradient(135deg, #10b981, #059669);
            color: #fff;
            border: none;
            padding: 12px;
            font-weight: 700;
            font-size: 14px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s ease;
        }

        .submit-btn:hover {
            filter: brightness(1.1);
        }

        .burst-btn {
            background: var(--bg-elevated);
            border: 1px solid var(--blue);
            color: var(--blue);
            padding: 10px;
            font-weight: 600;
            font-size: 12px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s;
        }

        .burst-btn:hover {
            background: var(--blue-glow);
            color: #fff;
        }

        /* Trades Tape */
        .trades-list {
            flex: 1;
            padding: 8px 12px;
            display: flex;
            flex-direction: column;
            gap: 4px;
            max-height: 480px;
            overflow-y: auto;
        }

        .trade-item {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            padding: 4px 6px;
            font-size: 11px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
        }

        .trade-item.buy .price { color: var(--green); }
        .trade-item.sell .price { color: var(--red); }

        /* Notification Toast */
        #toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: var(--bg-elevated);
            border: 1px solid var(--green);
            color: var(--text-primary);
            padding: 12px 20px;
            border-radius: 8px;
            font-size: 13px;
            display: none;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
            z-index: 999;
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-group">
            <div class="logo-badge">HFT</div>
            <div>
                <div class="logo-title">ChronosMatch</div>
                <div class="logo-tag">Zero-Copy Electronic Matching Core</div>
            </div>
        </div>
        <div class="header-stats">
            <div class="status-pill">
                <div class="pulse-dot"></div>
                ENGINE ACTIVE
            </div>
            <a href="/docs" target="_blank" style="color: var(--blue); font-size: 12px; text-decoration: none; font-weight: 600;">Swagger Docs ↗</a>
        </div>
    </header>

    <div class="metrics-bar mono">
        <div class="metric-card">
            <span class="metric-label">Median Latency (p50)</span>
            <span class="metric-val metric-highlight">3.20 µs</span>
        </div>
        <div class="metric-card">
            <span class="metric-label">Engine Throughput</span>
            <span class="metric-val metric-highlight">235,303 orders/s</span>
        </div>
        <div class="metric-card">
            <span class="metric-label">IPC Ring Buffer</span>
            <span class="metric-val">Lockless SPSC SharedMem</span>
        </div>
        <div class="metric-card">
            <span class="metric-label">Memory Architecture</span>
            <span class="metric-val">Zero-Copy Buffer Protocol</span>
        </div>
    </div>

    <main>
        <!-- Left: Order Book Ladder -->
        <section class="panel">
            <div class="panel-header">
                <span class="panel-title">L2 Order Book</span>
                <div class="symbol-tabs">
                    <button class="symbol-tab active" onclick="switchSymbol('BTCUSDT', this)">BTCUSDT</button>
                    <button class="symbol-tab" onclick="switchSymbol('ETHUSDT', this)">ETHUSDT</button>
                    <button class="symbol-tab" onclick="switchSymbol('AAPL', this)">AAPL</button>
                </div>
            </div>
            <div class="book-container mono">
                <div class="book-table-hdr">
                    <span>Price</span>
                    <span style="text-align: right;">Size</span>
                    <span style="text-align: right;">Total</span>
                </div>
                
                <!-- Asks (Red) -->
                <div id="asks-list" style="display: flex; flex-direction: column-reverse; min-height: 120px;"></div>

                <!-- Spread Banner -->
                <div class="spread-banner">
                    <span style="color: var(--text-muted);">Spread: <strong id="spread-val" style="color: var(--text-primary);">0.50</strong></span>
                    <span style="color: var(--text-muted);">BBO Mid: <strong id="mid-val" style="color: var(--blue);">65000.00</strong></span>
                </div>

                <!-- Bids (Green) -->
                <div id="bids-list" style="display: flex; flex-direction: column; min-height: 120px;"></div>
            </div>
        </section>

        <!-- Center: Interactive Order Entry -->
        <section class="panel">
            <div class="panel-header">
                <span class="panel-title">Order Placement Gateway</span>
                <span id="active-symbol-badge" class="mono" style="font-size: 11px; color: var(--blue); font-weight: 700;">BTCUSDT</span>
            </div>
            <div class="order-form">
                <div class="side-toggle">
                    <button type="button" class="side-btn buy active" id="btn-buy" onclick="setSide('BUY')">BUY</button>
                    <button type="button" class="side-btn sell" id="btn-sell" onclick="setSide('SELL')">SELL</button>
                </div>

                <div class="form-group">
                    <label class="form-label">Order Type</label>
                    <select class="form-select" id="input-type" onchange="togglePriceField()">
                        <option value="LIMIT">LIMIT ORDER</option>
                        <option value="MARKET">MARKET ORDER (AGGRESSIVE)</option>
                    </select>
                </div>

                <div class="form-group" id="group-price">
                    <label class="form-label">Limit Price ($)</label>
                    <input type="number" step="0.01" class="form-input mono" id="input-price" value="65000.00">
                </div>

                <div class="form-group">
                    <label class="form-label">Order Quantity (Units)</label>
                    <input type="number" min="1" step="1" class="form-input mono" id="input-qty" value="5">
                </div>

                <div class="form-group">
                    <label class="form-label">Time In Force (TIF)</label>
                    <select class="form-select" id="input-tif">
                        <option value="GTC">Good 'Til Cancelled (GTC)</option>
                        <option value="IOC">Immediate Or Cancel (IOC)</option>
                        <option value="FOK">Fill Or Kill (FOK)</option>
                    </select>
                </div>

                <button class="submit-btn" id="btn-submit" onclick="submitOrder()">Submit to Matching Engine</button>
                <button class="burst-btn" onclick="triggerSimulationBurst()">⚡ Simulate 10 Random Order Matches</button>
            </div>
        </section>

        <!-- Right: Execution Tape -->
        <section class="panel">
            <div class="panel-header">
                <span class="panel-title">Real-time Trade Tape</span>
                <span class="mono" style="font-size: 11px; color: var(--text-muted);" id="trade-count">0 trades</span>
            </div>
            <div class="book-table-hdr mono" style="padding: 6px 16px;">
                <span>Price</span>
                <span style="text-align: right;">Qty</span>
                <span style="text-align: right;">Time</span>
            </div>
            <div class="trades-list mono" id="trades-tape">
                <div style="color: var(--text-muted); font-size: 11px; text-align: center; padding: 24px;">No executions yet. Submit orders or trigger burst to match!</div>
            </div>
        </section>
    </main>

    <div id="toast"></div>

    <script>
        let currentSymbol = 'BTCUSDT';
        let currentSide = 'BUY';
        let orderCounter = 90000;
        let tradesTape = [];

        function setSide(side) {
            currentSide = side;
            document.getElementById('btn-buy').classList.toggle('active', side === 'BUY');
            document.getElementById('btn-sell').classList.toggle('active', side === 'SELL');
            const submitBtn = document.getElementById('btn-submit');
            if (side === 'BUY') {
                submitBtn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
                submitBtn.innerText = 'Submit BUY Order';
            } else {
                submitBtn.style.background = 'linear-gradient(135deg, #ef4444, #dc2626)';
                submitBtn.innerText = 'Submit SELL Order';
            }
        }

        function togglePriceField() {
            const type = document.getElementById('input-type').value;
            document.getElementById('group-price').style.display = type === 'MARKET' ? 'none' : 'flex';
        }

        function switchSymbol(symbol, btn) {
            currentSymbol = symbol;
            document.querySelectorAll('.symbol-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('active-symbol-badge').innerText = symbol;

            const baseP = symbol === 'BTCUSDT' ? 65000 : (symbol === 'ETHUSDT' ? 3500 : 150);
            document.getElementById('input-price').value = baseP.toFixed(2);
            fetchBookDepth();
        }

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.style.display = 'block';
            setTimeout(() => { t.style.display = 'none'; }, 3000);
        }

        async function fetchBookDepth() {
            try {
                const res = await fetch(`/api/depth/${currentSymbol}?depth=6`);
                if (!res.ok) return;
                const data = await res.json();
                renderOrderBook(data.bids, data.asks);
            } catch (e) {
                console.error(e);
            }
        }

        function renderOrderBook(bids, asks) {
            const asksContainer = document.getElementById('asks-list');
            const bidsContainer = document.getElementById('bids-list');

            const maxBidVol = Math.max(...bids.map(b => b.quantity), 1);
            const maxAskVol = Math.max(...asks.map(a => a.quantity), 1);
            const maxVol = Math.max(maxBidVol, maxAskVol);

            // Render Asks
            asksContainer.innerHTML = asks.slice(0, 6).map(a => `
                <div class="book-row ask">
                    <div class="bar" style="width: ${(a.quantity / maxVol) * 100}%;"></div>
                    <span class="ask-price">${a.price.toFixed(2)}</span>
                    <span style="text-align: right;">${a.quantity}</span>
                    <span style="text-align: right; color: var(--text-muted);">${(a.price * a.quantity).toFixed(0)}</span>
                </div>
            `).join('');

            // Render Bids
            bidsContainer.innerHTML = bids.slice(0, 6).map(b => `
                <div class="book-row bid">
                    <div class="bar" style="width: ${(b.quantity / maxVol) * 100}%;"></div>
                    <span class="bid-price">${b.price.toFixed(2)}</span>
                    <span style="text-align: right;">${b.quantity}</span>
                    <span style="text-align: right; color: var(--text-muted);">${(b.price * b.quantity).toFixed(0)}</span>
                </div>
            `).join('');

            const bestBid = bids.length ? bids[0].price : 0;
            const bestAsk = asks.length ? asks[0].price : 0;
            if (bestBid && bestAsk) {
                document.getElementById('spread-val').innerText = (bestAsk - bestBid).toFixed(2);
                document.getElementById('mid-val').innerText = ((bestAsk + bestBid) / 2).toFixed(2);
            }
        }

        async function submitOrder() {
            orderCounter++;
            const type = document.getElementById('input-type').value;
            const price = parseFloat(document.getElementById('input-price').value) || 0;
            const qty = parseInt(document.getElementById('input-qty').value) || 1;
            const tif = document.getElementById('input-tif').value;

            const payload = {
                order_id: orderCounter,
                client_id: 1,
                symbol: currentSymbol,
                side: currentSide,
                order_type: type,
                price: price,
                quantity: qty,
                tif: tif
            };

            try {
                const res = await fetch('/api/order', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (!res.ok) {
                    showToast('Error: ' + (data.detail || 'Order failed'));
                    return;
                }

                showToast(`Order #${orderCounter} submitted successfully!`);
                
                // Add executions to tape
                if (data.execution_reports) {
                    data.execution_reports.forEach(r => {
                        if (r.exec_type === 'TRADE') {
                            addTradeToTape(r.price, r.last_qty, r.side);
                        }
                    });
                }
                fetchBookDepth();
            } catch (e) {
                showToast('Failed to connect to matching engine API');
            }
        }

        function addTradeToTape(price, qty, side) {
            const timeStr = new Date().toLocaleTimeString();
            tradesTape.unshift({ price, qty, side, time: timeStr });
            if (tradesTape.length > 20) tradesTape.pop();

            document.getElementById('trade-count').innerText = `${tradesTape.length} trades`;
            const tapeContainer = document.getElementById('trades-tape');
            tapeContainer.innerHTML = tradesTape.map(t => `
                <div class="trade-item ${t.side.toLowerCase()}">
                    <span class="price">${t.price.toFixed(2)}</span>
                    <span style="text-align: right;">${t.qty}</span>
                    <span style="text-align: right; color: var(--text-muted);">${t.time}</span>
                </div>
            `).join('');
        }

        async function triggerSimulationBurst() {
            showToast('Simulating 10 market orders...');
            for (let i = 0; i < 10; i++) {
                orderCounter++;
                const side = Math.random() > 0.5 ? 'BUY' : 'SELL';
                const isLimit = Math.random() > 0.3;
                const offset = (Math.random() * 3).toFixed(2);
                const baseP = currentSymbol === 'BTCUSDT' ? 65000 : (currentSymbol === 'ETHUSDT' ? 3500 : 150);
                const price = side === 'BUY' ? (baseP - offset) : (baseP + offset);

                await fetch('/api/order', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        order_id: orderCounter,
                        client_id: 2,
                        symbol: currentSymbol,
                        side: side,
                        order_type: isLimit ? 'LIMIT' : 'MARKET',
                        price: parseFloat(price),
                        quantity: Math.floor(Math.random() * 5) + 1,
                        tif: 'GTC'
                    })
                });
            }
            fetchBookDepth();
        }

        // Auto poll depth every 1.5s
        fetchBookDepth();
        setInterval(fetchBookDepth, 1500);
    </script>
</body>
</html>
"""
