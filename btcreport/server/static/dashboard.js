// Dashboard: nhận cập nhật qua SSE, không reload trang.
// Dữ liệu khởi tạo do template nhét vào window.INITIAL.

(function () {
  var state = window.INITIAL || { symbols: [], status: {} };
  var lastPrice = {};

  var $ = function (id) { return document.getElementById(id); };

  function slug(v) {
    if (!v) return 'na';
    if (v.indexOf('LONG') >= 0) return 'long';
    if (v.indexOf('SHORT') >= 0) return 'short';
    if (v === 'N/A') return 'na';
    return 'neutral';
  }

  function usd(v, d) {
    if (v === null || v === undefined) return '—';
    return '$' + v.toLocaleString('en-US', {
      minimumFractionDigits: d === undefined ? 0 : d,
      maximumFractionDigits: d === undefined ? 0 : d
    });
  }

  function renderSymbols() {
    var host = $('cards');
    host.innerHTML = state.symbols.map(function (s) {
      var cv = (s.confluence && s.confluence.verdict) || 'N/A';
      var agree = (s.confluence && s.confluence.agree) || 0;
      var chg = s.change_24h;

      var tfs = (s.timeframes || []).map(function (t) {
        return '<div class="tf v-' + slug(t.verdict) + '">' +
          '<div class="tf-l">' + t.label + '</div>' +
          '<div class="tf-v c-' + slug(t.verdict) + '">' + t.verdict + '</div>' +
          '<div class="tf-r">RSI ' + Math.round(t.rsi) +
          ' ' + (t.macd_bull ? '▲' : '▼') + '</div>' +
          '</div>';
      }).join('');

      var risk = '';
      if (s.risk && s.risk.sl) {
        risk = '<div class="risk">' +
          '<span>Entry <b>' + usd(s.risk.entry, 2) + '</b></span>' +
          '<span>SL <b>' + usd(s.risk.sl, 2) + '</b></span>' +
          '<span>TP <b>' + usd(s.risk.tp, 2) + '</b></span>' +
          '</div>';
      } else if (s.levels) {
        risk = '<div class="risk">' +
          '<span>R1 <b>' + usd(s.levels.R1, 2) + '</b></span>' +
          '<span>S1 <b>' + usd(s.levels.S1, 2) + '</b></span>' +
          '<span>chưa có setup</span></div>';
      }

      return '<div class="sym v-' + slug(cv) + '" data-sym="' + s.symbol + '">' +
        '<div class="sym-head"><div>' +
        '<div class="sym-name">' + s.name + '</div>' +
        '<div class="sym-pair">' + s.symbol + '</div></div>' +
        '<div style="text-align:right">' +
        '<div class="price" id="p-' + s.symbol + '">' + usd(s.price, 2) + '</div>' +
        '<div class="chg ' + (chg >= 0 ? 'pos' : 'neg') + '" id="c-' + s.symbol + '">' +
        (chg === null || chg === undefined ? '—'
          : (chg >= 0 ? '▲ ' : '▼ ') + Math.abs(chg).toFixed(2) + '%') +
        '</div></div></div>' +
        '<div class="conf"><div class="conf-label">Confluence · ' + agree + '/4</div>' +
        '<div class="conf-val c-' + slug(cv) + '">' + cv + '</div></div>' +
        '<div class="tfs">' + tfs + '</div>' + risk +
        '</div>';
    }).join('');
  }

  function flashPrice(symbol, value) {
    var el = $('p-' + symbol);
    if (!el) return;
    var prev = lastPrice[symbol];
    el.textContent = usd(value, 2);
    if (prev !== undefined && value !== prev) {
      el.classList.remove('up', 'down');
      void el.offsetWidth;                 // ép trình duyệt vẽ lại
      el.classList.add(value > prev ? 'up' : 'down');
      setTimeout(function () { el.classList.remove('up', 'down'); }, 900);
    }
    lastPrice[symbol] = value;
  }

  function renderStatus() {
    var s = state.status || {};
    $('st-scan').textContent = s.last_scan_at ? s.last_scan_at.replace('T', ' ') : '—';
    $('st-price').textContent = s.last_price_at ? s.last_price_at.split('T')[1] : '—';
    $('st-viewers').textContent = s.viewers || 0;
    $('st-paused').innerHTML = s.paused
      ? '<span class="paused">⏸ ĐANG TẠM DỪNG</span>'
      : '<b>đang chạy</b>';
    tickCountdown();
  }

  function tickCountdown() {
    var s = state.status || {};
    if (!s.last_scan_at || !s.scan_interval) { $('st-next').textContent = '—'; return; }
    var next = new Date(s.last_scan_at).getTime() + s.scan_interval * 1000;
    var left = Math.max(0, Math.round((next - Date.now()) / 1000));
    var m = Math.floor(left / 60), ss = left % 60;
    $('st-next').textContent = m + 'm ' + (ss < 10 ? '0' : '') + ss + 's';
  }

  function setLive(on) {
    var d = $('dot');
    d.className = 'dot ' + (on ? 'live' : 'dead');
    $('live-text').textContent = on ? 'trực tiếp' : 'mất kết nối';
  }

  // ── SSE ────────────────────────────────────────────────────────────────────
  var es = null;
  function connect() {
    if (es) es.close();
    es = new EventSource('/events');

    es.addEventListener('hello', function (e) {
      state = JSON.parse(e.data);
      renderSymbols(); renderStatus(); setLive(true);
      state.symbols.forEach(function (s) { lastPrice[s.symbol] = s.price; });
    });

    es.addEventListener('price', function (e) {
      var d = JSON.parse(e.data);
      Object.keys(d.prices).forEach(function (sym) {
        var p = d.prices[sym];
        flashPrice(sym, p.last);
        var c = $('c-' + sym);
        if (c) {
          c.className = 'chg ' + (p.change_24h >= 0 ? 'pos' : 'neg');
          c.textContent = (p.change_24h >= 0 ? '▲ ' : '▼ ') +
            Math.abs(p.change_24h).toFixed(2) + '%';
        }
        var row = state.symbols.filter(function (s) { return s.symbol === sym; })[0];
        if (row) { row.price = p.last; row.change_24h = p.change_24h; }
      });
      state.status.last_price_at = new Date().toISOString().slice(0, 19);
      renderStatus();
    });

    es.addEventListener('signal', function (e) {
      var d = JSON.parse(e.data);
      state.symbols = d.symbols;
      state.status.last_scan_at = d.at;
      renderSymbols(); renderStatus();
      if (d.alerts && d.alerts.length) {
        $('st-alert').textContent = '⚡ ' +
          d.alerts.map(function (a) { return a.name; }).join(', ') + ' vừa đổi tín hiệu';
      }
    });

    es.addEventListener('report', function (e) {
      var d = JSON.parse(e.data);
      state.status.last_report_at = d.at;
      state.status.has_report = true;
      $('st-alert').textContent = '📄 Có báo cáo mới (' + d.verdict + ')';
      renderStatus();
    });

    es.onerror = function () {
      setLive(false);
      es.close();
      setTimeout(connect, 5000);          // tự nối lại, đừng bắt người dùng F5
    };
    es.onopen = function () { setLive(true); };
  }

  renderSymbols();
  renderStatus();
  state.symbols.forEach(function (s) { lastPrice[s.symbol] = s.price; });
  connect();
  setInterval(tickCountdown, 1000);
})();
