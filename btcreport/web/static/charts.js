// Chart.js config cho báo cáo BTC.
// Dữ liệu do template chèn vào window.REPORT_DATA — file này không chứa số liệu.
const D  = window.REPORT_DATA;
const d  = D.daily, h4 = D.h4, h1 = D.h1;

const labels   = d.labels;
const closes   = d.close;
const opens    = d.open;
const highs    = d.high;
const lows     = d.low;
const volumes  = d.volume;
const ma7      = d.ma7;
const ma25     = d.ma25;
const ma99     = d.ma99;
const rsiData  = d.rsi;
const macdData = d.macd;
const sigData  = d.macd_signal;
const histData = d.macd_hist;
const bbu      = d.bb_upper;
const bbl      = d.bb_lower;
const bbm      = d.bb_mid;

const labels4h = h4.labels, closes4h = h4.close, ma7_4h = h4.ma7, ma25_4h = h4.ma25;
const labels1h = h1.labels, closes1h = h1.close, ma7_1h = h1.ma7, ma25_1h = h1.ma25;

const gridColor = '#1e293b';
const font = { family:'Segoe UI', size:11 };

// ── PRICE CHART ─────────────────────────────────────────────────────────────
new Chart(document.getElementById('priceChart'), {
  type:'line',
  data:{
    labels,
    datasets:[
      { label:'BB Upper', data:bbu, borderColor:'#ef535055', borderWidth:1, borderDash:[4,4], pointRadius:0, fill:false, tension:.3 },
      { label:'BB Lower', data:bbl, borderColor:'#26c6da55', borderWidth:1, borderDash:[4,4], pointRadius:0, fill:false, tension:.3 },
      { label:'BB Mid',   data:bbm, borderColor:'#ffffff22', borderWidth:1, pointRadius:0, fill:false, tension:.3 },
      { label:'MA7',  data:ma7,  borderColor:'#ffd740', borderWidth:1.5, pointRadius:0, fill:false, tension:.3 },
      { label:'MA25', data:ma25, borderColor:'#40c4ff', borderWidth:1.5, pointRadius:0, fill:false, tension:.3 },
      { label:'MA99', data:ma99, borderColor:'#f48fb1', borderWidth:1.5, pointRadius:0, fill:false, tension:.3 },
      {
        label:'BTC Close', data:closes,
        borderColor:'#f59e0b', borderWidth:2,
        backgroundColor:'#f59e0b18',
        pointRadius:0, pointHoverRadius:5,
        fill:true, tension:.3
      },
    ]
  },
  options:{
    responsive:true, maintainAspectRatio:false,
    interaction:{ mode:'index', intersect:false },
    plugins:{
      legend:{ labels:{ color:'#94a3b8', font, boxWidth:16 } },
      tooltip:{ backgroundColor:'#0f172a', borderColor:'#334155', borderWidth:1, titleColor:'#f1f5f9', bodyColor:'#94a3b8' }
    },
    scales:{
      x:{ grid:{ color:gridColor }, ticks:{ color:'#475569', font, maxTicksLimit:12 } },
      y:{ grid:{ color:gridColor }, ticks:{ color:'#475569', font, callback:v=>'$'+v.toLocaleString() } }
    }
  }
});

// ── RSI ──────────────────────────────────────────────────────────────────────
new Chart(document.getElementById('rsiChart'), {
  type:'line',
  data:{
    labels,
    datasets:[
      { label:'RSI(14)', data:rsiData, borderColor:'#a78bfa', borderWidth:2, pointRadius:0, tension:.3, fill:false }
    ]
  },
  options:{
    responsive:true, maintainAspectRatio:false,
    plugins:{
      legend:{ labels:{ color:'#94a3b8', font } },
      tooltip:{ backgroundColor:'#0f172a', borderColor:'#334155', borderWidth:1, titleColor:'#f1f5f9', bodyColor:'#94a3b8' },
      annotation:{ annotations:{} }
    },
    scales:{
      x:{ grid:{ color:gridColor }, ticks:{ color:'#475569', font, maxTicksLimit:10 } },
      y:{ min:0, max:100, grid:{ color:gridColor },
           ticks:{ color:'#475569', font, stepSize:20 },
           afterDataLimits(scale){
             scale.max = 100;
             scale.min = 0;
           }
      }
    }
  }
});

// ── MACD ─────────────────────────────────────────────────────────────────────
new Chart(document.getElementById('macdChart'), {
  type:'bar',
  data:{
    labels,
    datasets:[
      { label:'MACD', data:macdData, type:'line', borderColor:'#60a5fa', borderWidth:1.5, pointRadius:0, tension:.3, fill:false },
      { label:'Signal', data:sigData, type:'line', borderColor:'#f87171', borderWidth:1.5, pointRadius:0, tension:.3, fill:false },
      { label:'Histogram', data:histData,
         backgroundColor: histData.map(v => v===null?'transparent':v>=0?'#00c85355':'#ff174455'),
         borderColor: histData.map(v => v===null?'transparent':v>=0?'#00c853':'#ff1744'),
         borderWidth:1
      },
    ]
  },
  options:{
    responsive:true, maintainAspectRatio:false,
    plugins:{ legend:{ labels:{ color:'#94a3b8', font } },
      tooltip:{ backgroundColor:'#0f172a', borderColor:'#334155', borderWidth:1, titleColor:'#f1f5f9', bodyColor:'#94a3b8' }
    },
    scales:{
      x:{ grid:{ color:gridColor }, ticks:{ color:'#475569', font, maxTicksLimit:10 } },
      y:{ grid:{ color:gridColor }, ticks:{ color:'#475569', font } }
    }
  }
});

function mkShortChart(elId, labels, closes, ma7, ma25, lineColor) {
  const el = document.getElementById(elId);
  if (!el || !labels.length) return;
  new Chart(el, {
    type:'line',
    data:{
      labels,
      datasets:[
        { label:'MA7',  data:ma7,  borderColor:'#ffd740', borderWidth:1.5, pointRadius:0, fill:false, tension:.3 },
        { label:'MA25', data:ma25, borderColor:'#40c4ff', borderWidth:1.5, pointRadius:0, fill:false, tension:.3 },
        { label:'Close', data:closes, borderColor:lineColor, borderWidth:2,
           backgroundColor:lineColor+'18', pointRadius:0, fill:true, tension:.3 }
      ]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      interaction:{ mode:'index', intersect:false },
      plugins:{
        legend:{ labels:{ color:'#94a3b8', font, boxWidth:16 } },
        tooltip:{ backgroundColor:'#0f172a', borderColor:'#334155', borderWidth:1, titleColor:'#f1f5f9', bodyColor:'#94a3b8' }
      },
      scales:{
        x:{ grid:{ color:gridColor }, ticks:{ color:'#475569', font, maxTicksLimit:12 } },
        y:{ grid:{ color:gridColor }, ticks:{ color:'#475569', font, callback:v=>'$'+v.toLocaleString() } }
      }
    }
  });
}
mkShortChart('chart4h', labels4h, closes4h, ma7_4h, ma25_4h, '#a78bfa');
mkShortChart('chart1h', labels1h, closes1h, ma7_1h, ma25_1h, '#34d399');

// ── VOLUME ───────────────────────────────────────────────────────────────────
new Chart(document.getElementById('volChart'), {
  type:'bar',
  data:{
    labels,
    datasets:[{
      label:'Volume (BTC)',
      data:volumes,
      backgroundColor: closes.map((c,i)=> c>=opens[i]?'#00c85355':'#ff174455'),
      borderColor:      closes.map((c,i)=> c>=opens[i]?'#00c853':'#ff1744'),
      borderWidth:1
    }]
  },
  options:{
    responsive:true, maintainAspectRatio:false,
    plugins:{ legend:{ labels:{ color:'#94a3b8', font } },
      tooltip:{ backgroundColor:'#0f172a', borderColor:'#334155', borderWidth:1, titleColor:'#f1f5f9', bodyColor:'#94a3b8' }
    },
    scales:{
      x:{ grid:{ color:gridColor }, ticks:{ color:'#475569', font, maxTicksLimit:12 } },
      y:{ grid:{ color:gridColor }, ticks:{ color:'#475569', font } }
    }
  }
});