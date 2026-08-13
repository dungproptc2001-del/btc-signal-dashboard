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

  // ── Nhật ký tín hiệu ───────────────────────────────────────────────────────
  var feed = [];

  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function gioVN(iso) {
    // Chuỗi đã kèm offset +07:00 nên cắt thẳng, KHÔNG qua new Date():
    // qua Date là trình duyệt đổi sang múi giờ của khách, sai ý "giờ Việt Nam".
    if (!iso) return '—';
    var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
    return m ? (m[4] + ':' + m[5] + ' ' + m[3] + '/' + m[2]) : iso;
  }

  function truoc(iso) {
    if (!iso) return '';
    var s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return 'vừa xong';
    if (s < 3600) return Math.floor(s / 60) + ' phút trước';
    if (s < 86400) return Math.floor(s / 3600) + ' giờ trước';
    return Math.floor(s / 86400) + ' ngày trước';
  }

  // ── Chấm điểm ──────────────────────────────────────────────────────────────
  var NHAN = {
    win:        ['✓ Thắng',      'win'],
    loss:       ['✗ Thua',       'loss'],
    expired:    ['⌛ Hết hạn',    'expired'],
    superseded: ['↺ Đổi hướng',  'superseded'],
    skipped:    ['– Bỏ qua',     'skipped'],
    open:       ['● Đang chạy',  'open']
  };

  function huyHieu(o) {
    if (!o || !o.status) return '';
    var n = NHAN[o.status] || [o.status, 'open'];
    var r = (o.r === null || o.r === undefined) ? '' : ' ' + (o.r > 0 ? '+' : '') + o.r + 'R';
    return '<span class="oc ' + n[1] + '">' + n[0] + r +
           (o.ambiguous ? ' <b title="Một nến chạm cả TP lẫn SL – tính là thua">⚠</b>' : '') +
           '</span>';
  }

  function khoi(tk, ten) {
    var c = tk.counts || {};
    var chip = function (k) {
      var n = NHAN[k];
      return '<span class="oc ' + n[1] + '">' + n[0] + ' <b>' + (c[k] || 0) + '</b></span>';
    };

    // Tỷ lệ do server quyết định có hiện hay không. KHÔNG tự tính lấy từ counts:
    // ẩn tỷ lệ lúc mẫu còn bé là một luật, không phải gợi ý — và nếu tính ở đây
    // thì luật đó sẽ lặng lẽ biến mất lần đầu ai đó sửa giao diện.
    var ty_le = tk.win_rate === null || tk.win_rate === undefined
      ? '<span class="chua-du">Chưa đủ mẫu để nói tỷ lệ: <b>n=' + tk.n + '</b>/' +
        tk.min_n + ' — con số trên mẫu bé là nhiễu, không phải kết luận</span>'
      : '<span class="ty-le">Tỷ lệ thắng <b>' + tk.win_rate + '%</b> ' +
        '<span class="ago">(n=' + tk.n + ')</span></span>';

    var r = tk.avg_r === null || tk.avg_r === undefined ? '' :
      '<span class="ty-le">R trung bình <b>' + (tk.avg_r > 0 ? '+' : '') + tk.avg_r +
      '</b> <span class="ago">(n=' + tk.n_r + ')</span></span>';

    return '<div class="stat-row">' +
      (ten ? '<span class="sym">' + esc(ten) + '</span>' : '<span class="sym tong">TỔNG</span>') +
      ty_le + r +
      '<span class="chips">' +
        chip('win') + chip('loss') + chip('expired') +
        chip('superseded') + chip('open') + chip('skipped') +
      '</span></div>';
  }

  function renderStats(tk) {
    var host = $('stats-body');
    if (!host || !tk || !tk.overall) return;
    var html = khoi(tk.overall, null);
    Object.keys(tk.by_symbol || {}).forEach(function (sym) {
      html += khoi(tk.by_symbol[sym], sym);
    });
    html += '<div class="stat-note">Thắng = chạm TP trước SL · hết hạn sau ' +
      tk.expiry_days + ' ngày · dò bằng nến 1H · R:R 1:' + tk.rr +
      ' · <b>hết hạn tính vào mẫu số</b>, đổi hướng thì không</div>';
    host.innerHTML = html;
  }

  function tailStats() {
    fetch('/api/signals/stats', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d) renderStats(d); })
      .catch(function () { /* thống kê hỏng không được làm sập cả trang */ });
  }

  function dongTinHieu(e, i, moi) {
    var tre = '';
    if (e.first_seen_at && e.first_seen_at !== e.at) {
      var p = Math.round((new Date(e.at) - new Date(e.first_seen_at)) / 60000);
      if (p > 0) tre = ' <span class="ago">(thấy từ ' + gioVN(e.first_seen_at) +
                       ', xác nhận sau ' + p + 'p)</span>';
    }
    return '' +
      '<div class="sig' + (moi ? ' new' : '') + '" data-i="' + i + '">' +
        '<span class="t">' + gioVN(e.at) + '</span>' +
        '<span class="sym">' + esc(e.name) + '</span>' +
        (e.from ? '<span class="arrow">' + esc(e.from) + ' →</span>' : '') +
        '<span class="tag ' + slug(e.to) + '">' + esc(e.to || '—') + '</span>' +
        (e.telegram_ok === false
          ? '<span class="warn">⚠ Telegram lỗi</span>' : '') +
        huyHieu(e.outcome) +
        '<span class="px">' + usd(e.price, 2) + '</span>' +
        '<span class="ago">' + truoc(e.at) + '</span>' +
      '</div>' +
      '<div class="sig-detail" data-d="' + i + '"><pre>' + esc(e.text) + tre + '</pre></div>';
  }

  function renderFeed(iMoi) {
    var host = $('signals-list');
    if (!host) return;
    if (!feed.length) {
      host.innerHTML = '<div class="signals-empty">Chưa có tín hiệu nào. ' +
        'Nhật ký bắt đầu từ lúc bật tính năng này – không có lịch sử cũ.</div>';
      return;
    }
    host.innerHTML = feed.map(function (e, i) {
      return dongTinHieu(e, i, iMoi !== undefined && i < iMoi);
    }).join('');
  }

  document.addEventListener('click', function (ev) {
    var row = ev.target.closest ? ev.target.closest('.sig') : null;
    if (!row) return;
    var d = document.querySelector('.sig-detail[data-d="' + row.dataset.i + '"]');
    if (d) d.classList.toggle('open');
  });

  function tailFeed() {
    fetch('/api/signals/history?limit=20', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : { entries: [] }; })
      .then(function (d) { feed = d.entries || []; renderFeed(); })
      .catch(function () { /* feed hỏng không được làm sập cả trang */ });
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

  // ── Tuổi dữ liệu ───────────────────────────────────────────────────────────
  // Đếm bằng SỐ GIÂY, tuyệt đối không parse `last_scan_at`. Mốc đó server ghi bằng
  // giờ địa phương KHÔNG kèm offset, nên new Date() ở trình duyệt múi giờ khác lệch
  // hàng tiếng — băng đỏ sẽ bật vĩnh viễn dù hệ thống hoàn toàn khoẻ. Khoảng cách
  // thì không có múi giờ nào để sai.
  var ageBase = null, ageAt = 0;

  function markAge(seconds) {
    ageBase = (seconds === null || seconds === undefined) ? null : seconds;
    ageAt   = Date.now();
  }

  function scanAge() {
    if (ageBase === null) return null;
    return ageBase + Math.round((Date.now() - ageAt) / 1000);
  }

  function doDai(s) {
    var g = Math.floor(s / 3600), p = Math.round((s % 3600) / 60);
    if (g <= 0) return p + ' phút';
    return g + ' giờ' + (p ? ' ' + p + ' phút' : '');
  }

  function renderStatus() {
    var s = state.status || {};
    $('st-scan').textContent = s.last_scan_at ? s.last_scan_at.replace('T', ' ') : '—';
    $('st-price').textContent = s.last_price_at ? s.last_price_at.split('T')[1] : '—';
    $('st-viewers').textContent = s.viewers || 0;
    $('st-paused').innerHTML = s.standby
      ? '<span class="paused">🔌 ĐANG NGHỈ</span>'
      : (s.paused ? '<span class="paused">⏸ ĐANG TẠM DỪNG</span>' : '<b>đang chạy</b>');

    var b = $('standby-banner');
    if (b) b.style.display = s.standby ? 'block' : 'none';
    tickCountdown();
  }

  function tickCountdown() {
    var s = state.status || {}, age = scanAge();

    if (age === null || !s.scan_interval) {
      $('st-next').textContent = '—';
    } else {
      var left = Math.max(0, s.scan_interval - age);
      var m = Math.floor(left / 60), ss = left % 60;
      $('st-next').textContent = m + 'm ' + (ss < 10 ? '0' : '') + ss + 's';
    }

    var b = $('stale-banner');
    if (!b) return;
    // Ngưỡng lấy của server chứ không tự đặt ở đây. Nghỉ và tạm dừng là chủ nhà chủ
    // động, không phải hỏng — báo động lúc đó là tự tạo báo động giả cho chính mình.
    var cu = age !== null && s.stale_after && age > s.stale_after
             && !s.paused && !s.standby;
    b.style.display = cu ? 'block' : 'none';
    if (cu) $('stale-age').textContent = doDai(age);
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
      markAge(state.status ? state.status.scan_age_seconds : null);
      renderSymbols(); renderStatus(); setLive(true);
      state.symbols.forEach(function (s) { lastPrice[s.symbol] = s.price; });
    });

    es.addEventListener('power', function (e) {
      var d = JSON.parse(e.data);
      if (!state.status) state.status = {};
      state.status.standby = d.standby;
      renderStatus();
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
      markAge(0);                          // vừa quét xong, tuổi về không
      renderSymbols(); renderStatus();
      if (d.alerts && d.alerts.length) {
        $('st-alert').textContent = '⚡ ' +
          d.alerts.map(function (a) { return a.name; }).join(', ') + ' vừa đổi tín hiệu';
      }
      // Tín hiệu mới chèn lên đầu nhật ký kèm nháy sáng, không cần reload
      if (d.entries && d.entries.length) {
        d.entries.forEach(function (x) { if (!x.outcome) x.outcome = { status: 'open' }; });
        feed = d.entries.slice().reverse().concat(feed).slice(0, 20);
        renderFeed(d.entries.length);
        tailStats();
      }
    });

    es.addEventListener('outcome', function (e) {
      var d = JSON.parse(e.data);
      // Gắn kết quả vào đúng dòng đang hiện, khỏi tải lại cả nhật ký
      (d.settled || []).forEach(function (r) {
        feed.forEach(function (x) { if ((x.id || (x.symbol + '@' + x.at)) === r.id) x.outcome = r; });
      });
      renderFeed();
      tailStats();
      state.status.last_score_at = d.at;
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

  markAge(state.status ? state.status.scan_age_seconds : null);
  renderSymbols();
  renderStatus();
  tailFeed();
  tailStats();
  state.symbols.forEach(function (s) { lastPrice[s.symbol] = s.price; });
  connect();
  setInterval(tickCountdown, 1000);
  setInterval(function () { if (feed.length) renderFeed(); }, 60000);  // làm mới "2 giờ trước"
})();
