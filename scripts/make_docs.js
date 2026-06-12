const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, HeadingLevel, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageBreak, Header, Footer, PageNumber
} = require('docx');
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, '..');

// ── Shared styles ─────────────────────────────────────────────────────────────
const STYLES = {
  default: { document: { run: { font: 'Arial', size: 22 } } },
  paragraphStyles: [
    { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
      run: { size: 36, bold: true, font: 'Arial', color: '1F3864' },
      paragraph: { spacing: { before: 360, after: 120 }, outlineLevel: 0 } },
    { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
      run: { size: 28, bold: true, font: 'Arial', color: '2E75B6' },
      paragraph: { spacing: { before: 240, after: 80 }, outlineLevel: 1 } },
    { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
      run: { size: 24, bold: true, font: 'Arial', color: '404040' },
      paragraph: { spacing: { before: 160, after: 60 }, outlineLevel: 2 } },
  ]
};

const NUMBERING = {
  config: [
    { reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•',
        alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    { reference: 'sub', levels: [{ level: 0, format: LevelFormat.BULLET, text: '◦',
        alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 1080, hanging: 360 } } } }] },
    { reference: 'nums', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.',
        alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  ]
};

const SECTION_PROPS = {
  page: {
    size: { width: 12240, height: 15840 },
    margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 }
  }
};

const bdr = (c='CCCCCC') => ({ style: BorderStyle.SINGLE, size: 1, color: c });
const hdrBorder = (c='2E75B6') => ({ style: BorderStyle.SINGLE, size: 4, color: c });
const noBorder = () => ({ style: BorderStyle.NONE, size: 0, color: 'FFFFFF' });

function h1(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
}
function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
}
function h3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(text)] });
}
function body(text, opts={}) {
  return new Paragraph({ spacing: { after: 80 }, children: [new TextRun({ text, ...opts })] });
}
function bullet(text, bold='', ref='bullets') {
  const runs = [];
  if (bold) runs.push(new TextRun({ text: bold, bold: true, font: 'Arial', size: 22 }));
  if (text) runs.push(new TextRun({ text: bold ? ' ' + text : text, font: 'Arial', size: 22 }));
  return new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 60 }, children: runs });
}
function spacer(n=1) {
  return Array.from({ length: n }, () => new Paragraph({ children: [new TextRun('')] }));
}
function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}
function ruled(color='2E75B6') {
  return new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color, space: 1 } },
    spacing: { after: 120 },
    children: [new TextRun('')]
  });
}

// ── Table helpers ─────────────────────────────────────────────────────────────
function makeTable(headers, rows, colWidths) {
  const totalW = colWidths.reduce((a, b) => a + b, 0);
  const borders = { top: bdr(), bottom: bdr(), left: bdr(), right: bdr(), insideH: bdr(), insideV: bdr() };
  const hdrBorders = { top: hdrBorder(), bottom: hdrBorder(), left: bdr(), right: bdr(), insideH: bdr(), insideV: bdr() };

  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => new TableCell({
      borders: hdrBorders,
      width: { size: colWidths[i], type: WidthType.DXA },
      shading: { fill: '1F3864', type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: h, bold: true, color: 'FFFFFF', font: 'Arial', size: 20 })] })]
    }))
  });

  const dataRows = rows.map((row, ri) => new TableRow({
    children: row.map((cell, ci) => new TableCell({
      borders,
      width: { size: colWidths[ci], type: WidthType.DXA },
      shading: { fill: ri % 2 === 0 ? 'F5F8FF' : 'FFFFFF', type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({ children: [new TextRun({ text: cell, font: 'Arial', size: 20 })] })]
    }))
  }));

  return new Table({ width: { size: totalW, type: WidthType.DXA }, columnWidths: colWidths,
    rows: [headerRow, ...dataRows] });
}

// ── Cover page ────────────────────────────────────────────────────────────────
function coverPage(title, subtitle, date, version) {
  return [
    ...spacer(8),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 240 },
      children: [new TextRun({ text: title, bold: true, size: 52, font: 'Arial', color: '1F3864' })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 120 },
      children: [new TextRun({ text: subtitle, size: 28, font: 'Arial', color: '2E75B6' })]
    }),
    ruled(),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 80 },
      children: [new TextRun({ text: `Date: ${date}  |  Version: ${version}`, size: 22, font: 'Arial', color: '666666' })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: 'Aligned Automation Services Pvt. Ltd.', size: 22, font: 'Arial', color: '666666' })]
    }),
    pageBreak()
  ];
}

function makeHeader(title) {
  return new Header({
    children: [
      new Paragraph({
        border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: '2E75B6', space: 1 } },
        tabStops: [{ type: 'right', position: 9360 }],
        children: [
          new TextRun({ text: title, bold: true, font: 'Arial', size: 18, color: '1F3864' }),
          new TextRun({ text: '\t', font: 'Arial', size: 18 }),
          new TextRun({ text: 'Aligned Automation Services', font: 'Arial', size: 18, color: '666666' })
        ]
      })
    ]
  });
}

function makeFooter() {
  return new Footer({
    children: [
      new Paragraph({
        border: { top: { style: BorderStyle.SINGLE, size: 4, color: '2E75B6', space: 1 } },
        tabStops: [{ type: 'right', position: 9360 }],
        alignment: AlignmentType.LEFT,
        children: [
          new TextRun({ text: 'CONFIDENTIAL', font: 'Arial', size: 16, color: '999999' }),
          new TextRun({ text: '\tPage ', font: 'Arial', size: 16, color: '666666' }),
          new TextRun({ children: [PageNumber.CURRENT], font: 'Arial', size: 16, color: '666666' })
        ]
      })
    ]
  });
}


// ══════════════════════════════════════════════════════════════════════════════
// DOCUMENT 1 — FEATURES
// ══════════════════════════════════════════════════════════════════════════════
function buildFeatures() {
  const children = [
    ...coverPage(
      'RTA Monitor',
      'System Features & Capabilities',
      'June 2026', 'V3'
    ),

    h1('Executive Summary'),
    ruled(),
    body('The RTA (Real-Time Analyst) Monitor is an AI-powered contact centre SLA monitoring platform managing 10 global regions and 60+ skill queues in real time. Every 60 seconds it scrapes live dashboard data, analyses queue health, fires escalation levers, monitors individual agent behaviour, and provides an AI chatbot for live and historical queries. The system is architected to scale from the current 10 regions to 700+ queues with minimal configuration changes — only config.json needs new entries.'),
    ...spacer(1),

    // ── Section A ─────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Section A — Current Features (Built & Live)'),
    ruled(),

    h2('1. Multi-Region Real-Time Monitoring'),
    bullet('Simultaneously monitors 10 global regions: India, China, Australia, EMEA, Hong Kong, Malaysia, Korea, Thailand, Brazil, Taiwan'),
    bullet('Each region runs as an independent Python thread — no region blocks another'),
    bullet('Poll cycle: every 60 seconds per region (configurable in config.json)'),
    bullet('Metrics captured per skill per poll: SLA%, queue depth, OCW (Oldest Call Waiting), agents available/on calls/on AUX/headcount, offered calls, acceptable calls'),
    bullet('All metrics persisted to SQLite history database with 7-day rolling window'),
    ...spacer(1),

    h2('2. LangGraph Agent Pipeline (4-Agent Orchestration)'),
    bullet('Agent 1 (Scraper):', 'scrapes live HTML dashboard for queue metrics every 60 seconds'),
    bullet('Router:', 'evaluates every skill after each scrape — no hardcoded if/else chains — decides which agents to invoke'),
    bullet('Agent 2 (Analyst):', 'fires on queue pressure or OCW breach, sends LLM-powered named recommendations to Teams'),
    bullet('Agent 3 (Lever):', 'fires Amber/Red/Black escalation levers when SLA crosses thresholds, updates Excel, emails recipients'),
    bullet('Agent 4 (CMS Monitor):', 'runs independently in its own thread — monitors individual agent AHT, AUX duration, and ACW'),
    bullet('Dual-mode operation:', 'Full Pipeline (all 4 agents + alerts) or Scrape Only (data collection, no alerts)'),
    ...spacer(1),

    h2('3. Intelligent Lever System — One-Shot + Recovery'),
    bullet('Three escalation levers: Amber (SLA < 90%), Red (SLA < 80%), Black (SLA < 70%)'),
    bullet('One-shot logic:', 'each lever fires ONLY ONCE per SLA band crossing — never fires repeatedly for the same drop'),
    bullet('Progressive escalation:', 'if SLA drops from 85% to 65% in one poll, all three levers fire in the same cycle'),
    bullet('Recovery detection:', 'queue=0 AND avail>0 AND SLA>=90% simultaneously triggers Teams RESOLVED card and resets lever history'),
    bullet('Every lever fire updates an Excel report file and emails all configured recipients'),
    ...spacer(1),

    h2('4. Agent 4 — Individual Agent CMS Monitoring (Unique Feature)'),
    bullet('Monitors individual agents — not just skill queues — every 60 seconds'),
    bullet('AHT breach detection:', 'alerts when any agent\'s current call exceeds their skill AHT target by 10% — agent named in the alert'),
    bullet('AUX time breach:', 'per-AUX-code time limits (Break=15min, Lunch=30min, Meeting=60min) — named agents with exact durations'),
    bullet('ACW monitoring:', 'alerts when agents stay in After-Call-Work beyond configurable target (default 5 min)'),
    bullet('AUX Count Gate (smart suppression):', 'if total AUX agents <= skill\'s aux_threshold, ALL time-based AUX alerts are suppressed — prevents alert fatigue for healthy large teams'),
    bullet('Per-skill active toggle:', 'individual skills can be deactivated without stopping the region'),
    ...spacer(1),

    h2('5. Per-Skill Configuration (60+ Skills)'),
    bullet('Every skill has individual config: AHT target (min), OCW threshold override (sec), active/inactive toggle, aux_threshold'),
    bullet('Config is hot-reloaded every poll cycle — no restart needed for threshold changes'),
    bullet('Per-skill OCW threshold overrides global — fine-grained control per queue type'),
    bullet('AHT targets by skill type: ProDB=24min, Elite=22min, LicKeys=26min, VICHW=20min, CritAcct=28min'),
    ...spacer(1),

    h2('6. Multi-Provider LLM with Auto-Failover'),
    bullet('Three providers in priority order: NVIDIA NIM 70B (primary), Groq (fallback), Gemini (secondary)'),
    bullet('Round-robin key rotation across all API keys in the pool'),
    bullet('Automatic 429 (rate limit) handling: rotate key + exponential backoff (max 30s)'),
    bullet('Per-region locks: only one LLM call per region at a time — fully thread-safe'),
    bullet('LLM invoked only when actionable: Agent 2 skips LLM if no AUX agents exist to move (no cost, no delay)'),
    ...spacer(1),

    h2('7. AI Chatbot — Live + History Modes'),
    bullet('Live mode:', 'intelligent context builder detects region, topic, applies thresholds, includes named agents from CMS'),
    bullet('History mode:', 'LLM generates SQL → validated → executed on 7-day SQLite DB → aggregated → second LLM for formatted answer'),
    bullet('SQL safety:', 'only SELECT allowed — any DROP/UPDATE/DELETE raises error before execution'),
    bullet('Range query aggregation:', 'yesterday/past week queries produce scorecard (min/max/avg SLA, peak queue, time-in-band) saving ~80% tokens vs raw rows'),
    bullet('Anti-hallucination guards:', 'never invents agent names or SLA values — shows "pending CMS data" when names unavailable'),
    bullet('Answer formatting driven entirely by rules.yaml — no code changes to modify chatbot style'),
    ...spacer(1),

    h2('8. React Dashboard (Real-Time)'),
    bullet('10 region cards: flag emoji, average SLA, live band badge, sparkline chart, breach count, lever count, worst skill in footer'),
    bullet('Badge colour based on average SLA — not worst-skill — prevents one SEVERE from painting the entire region card red'),
    bullet('Worst skill still shown separately in the card footer with its real band'),
    bullet('Health Summary Bar: overall SLA%, band counts (SEVERE/CRITICAL/WARNING/HEALTHY/EXCELLENT), mini traffic-light dots per region'),
    bullet('SocketIO real-time updates — dashboard refreshes automatically without page reload'),
    bullet('Dark/Light theme toggle (persists to localStorage), Mode selector, Start/Stop/Restart controls'),
    ...spacer(1),

    h2('9. Master Rulebook — rules.yaml'),
    bullet('All business rules, operational thresholds, chatbot formatting rules, SQL rules, and anti-hallucination guards in ONE YAML file'),
    bullet('No code change needed to modify any rule — edit rules.yaml only'),
    bullet('Automatically injected into every LLM prompt by prompt_loader.py'),
    bullet('10 sections: SLA bands, lever thresholds, routing rules, Agent 4 rules, data integrity, LLM rules, SQL rules, chatbot answer rules, output formats'),
    ...spacer(1),

    h2('10. Microsoft Teams Integration'),
    bullet('Adaptive Card alerts via Power Automate webhooks (one webhook per region)'),
    bullet('Agent 2 alert: skill, SLA%, queue depth, OCW, and named AUX agents to pull back with durations'),
    bullet('Agent 3 alert: lever colour (Amber/Red/Black), region, skill, SLA%, recommended action'),
    bullet('Agent 4 alert: per-agent AHT/AUX/ACW overruns with agent names and exact durations'),
    bullet('Recovery alert: green RESOLVED Adaptive Card when skill returns to healthy state'),
    bullet('Staggered startup: Agent 4 threads start 6 seconds apart — prevents simultaneous alert flood on startup'),
    ...spacer(1),

    h2('11. Data Persistence (SQLite + JSON)'),
    bullet('SQLite history.db with WAL mode: concurrent reads while 10 region threads write simultaneously'),
    bullet('skill_history table: one row per skill per poll (SLA, band, queue, OCW, lever fired, breach reasons, root cause)'),
    bullet('cms_history table: one row per agent per poll (state, AUX reason, time in state, time in seconds)'),
    bullet('live_state.json: latest snapshot per region (chatbot live mode reads this)'),
    bullet('cms_agents.json: latest per-skill agent state (chatbot agent recommendations read this)'),
    bullet('Atomic writes with .tmp-rename to handle OneDrive sync locking (Windows environment)'),
    bullet('Shared cross-region lock for cms_agents.json via sys.modules singleton'),
    ...spacer(1),

    h2('12. Excel Reporting'),
    bullet('Agent 3 updates a configured Excel file on every lever fire'),
    bullet('Configurable file path via agent3.excel_path in config.json'),
    bullet('Email notifications to configured recipient list on each lever fire'),
    ...spacer(1),

    // ── Section B ─────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Section B — Future Features (Scaling to 700+ Queues)'),
    ruled(),

    h2('1. PostgreSQL Migration'),
    body('Current SQLite is adequate for 10 regions (~1M rows/month). At 50+ regions, migrate history.db to PostgreSQL for connection pooling, partitioning by region/date, and better concurrent write performance. Only core/history.py changes needed — no application logic changes.'),
    ...spacer(1),

    h2('2. Dashboard Pagination & Regional Grouping'),
    body('At 70+ regions, group cards by geography (APJ / EMEA / LATAM) with pagination within groups. Drill-down: click a group to see all regions. Summary roll-up: APJ SLA, EMEA SLA, LATAM SLA at the top level.'),
    ...spacer(1),

    h2('3. HTML Template Generator'),
    body('Script to auto-generate all ui/RTA_<TAG>.html files from a single template + config.json. Eliminates manual maintenance of 70+ dashboard files and prevents copy-paste errors.'),
    ...spacer(1),

    h2('4. Predictive SLA Alerts (Pre-emptive)'),
    body('Use 7-day history to detect day-of-week patterns. Alert supervisors 15 minutes BEFORE predicted SLA drop: "India ProDB historically drops to WARNING at 14:00 — recommend adding agents now." Simple ARIMA or LSTM time-series model per skill.'),
    ...spacer(1),

    h2('5. Agent Fatigue Detection'),
    body('Track individual agent AUX patterns across the shift. Alert when an agent takes 3+ breaks in 4 hours (fatigue signal). Distinguish fatigue (repeated short breaks) from genuine needs (single long break). Supervisor alert names the agent and shows total AUX time.'),
    ...spacer(1),

    h2('6. Shift Scheduling Recommendation'),
    body('Use historical queue peaks to recommend optimal agent headcount per skill per hour. "Peak queue at India ProDB historically hits 8 calls at 14:30 — schedule 2 extra agents from 14:00." Export recommendations to Excel or HR system.'),
    ...spacer(1),

    h2('7. Cross-Region Benchmarking'),
    body('Automated weekly report comparing all regions by skill type. "Best: Korea ProDB (avg 94.1%) | Worst: India VICHW (avg 72.3%)." Identifies consistently underperforming regions for root cause analysis.'),
    ...spacer(1),

    h2('8. Auto-Remediation (Supervised)'),
    body('Supervisor-approved automatic actions: when Black lever fires + queue > 10, auto-send message to backup pool. Requires one-click confirmation in Teams Adaptive Card. Full audit trail of every automated action taken.'),
    ...spacer(1),

    h2('9. Real-Time Anomaly Detection'),
    body('Statistical baseline per skill per hour-of-day per day-of-week. Alert when metric exceeds 2 standard deviations from baseline. Catches unusual patterns not covered by static thresholds (e.g. unexpected 9 AM queue spike on a normally quiet morning).'),
    ...spacer(1),

    h2('10. Multi-Tenant / Multi-Client Support'),
    body('Add client_id to every config and data record. Separate Teams webhooks, Excel reports, and chatbot sessions per client. Single deployment serving multiple contact centre clients with full data isolation.'),
    ...spacer(1),

    h2('11. Voice & WhatsApp Chatbot'),
    body('Extend AI chatbot to WhatsApp Business API and voice assistants. Supervisors can ask "What is Korea SLA right now?" by voice. Proactive push alerts to WhatsApp when Black lever fires.'),
    ...spacer(1),

    h2('12. Grafana / Power BI Integration'),
    body('Expose history.db metrics via REST API or Prometheus endpoint. Native Grafana dashboards with live SLA charts, queue heatmaps, and lever history timeline. Auto-generated Power BI weekly client SLA reports from history.db.'),
    ...spacer(1),

    // ── Section C ─────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Section C — Unique Differentiators'),
    ruled(),
    body('What makes RTA Monitor different from standard monitoring tools:'),
    ...spacer(1),

    new Paragraph({ numbering: { reference: 'nums', level: 0 }, spacing: { after: 80 },
      children: [new TextRun({ text: 'LangGraph Agent Orchestration ', bold: true, font: 'Arial', size: 22 }),
        new TextRun({ text: '— not a simple polling script. A real multi-agent pipeline where each agent has a specific role and the router decides dynamically which agents to invoke based on live conditions.', font: 'Arial', size: 22 })] }),

    new Paragraph({ numbering: { reference: 'nums', level: 0 }, spacing: { after: 80 },
      children: [new TextRun({ text: 'LLM-Powered Named Recommendations ', bold: true, font: 'Arial', size: 22 }),
        new TextRun({ text: '— Agent 2 names specific agents currently on AUX, how long they have been on break, and recommends exactly who to pull back in priority order. Never generic advice.', font: 'Arial', size: 22 })] }),

    new Paragraph({ numbering: { reference: 'nums', level: 0 }, spacing: { after: 80 },
      children: [new TextRun({ text: 'AUX Count Gate ', bold: true, font: 'Arial', size: 22 }),
        new TextRun({ text: '— intelligent alert suppression that knows healthy large teams (ProDB) tolerate more AUX agents before alerting, while struggling small teams (VICHW) need tighter control. Prevents alert fatigue without missing real issues.', font: 'Arial', size: 22 })] }),

    new Paragraph({ numbering: { reference: 'nums', level: 0 }, spacing: { after: 80 },
      children: [new TextRun({ text: 'One-Shot Lever with Recovery Re-arm ', bold: true, font: 'Arial', size: 22 }),
        new TextRun({ text: '— levers fire once, never repeatedly for the same breach. But they automatically re-arm after genuine recovery so the next drop triggers a fresh alert.', font: 'Arial', size: 22 })] }),

    new Paragraph({ numbering: { reference: 'nums', level: 0 }, spacing: { after: 80 },
      children: [new TextRun({ text: 'Unified Rulebook (rules.yaml) ', bold: true, font: 'Arial', size: 22 }),
        new TextRun({ text: '— every business rule, threshold, chatbot format, and SQL constraint lives in one YAML file. Operations teams can tune the entire system\'s behaviour without touching a single line of code.', font: 'Arial', size: 22 })] }),

    new Paragraph({ numbering: { reference: 'nums', level: 0 }, spacing: { after: 80 },
      children: [new TextRun({ text: 'History Chatbot with SQL Generation ', bold: true, font: 'Arial', size: 22 }),
        new TextRun({ text: '— natural language queries against 7 days of history. Ask "What was India ProDB doing yesterday afternoon?" and get a scorecard table with narrative summary from real data.', font: 'Arial', size: 22 })] }),

    new Paragraph({ numbering: { reference: 'nums', level: 0 }, spacing: { after: 80 },
      children: [new TextRun({ text: 'Anti-Hallucination by Design ', bold: true, font: 'Arial', size: 22 }),
        new TextRun({ text: '— the chatbot refuses to invent data. CMS names unavailable? Show counts only. No lever fired? State it explicitly. Built for production trust.', font: 'Arial', size: 22 })] }),
  ];

  return new Document({
    styles: STYLES,
    numbering: NUMBERING,
    sections: [{
      properties: SECTION_PROPS,
      headers: { default: makeHeader('RTA Monitor — System Features & Capabilities') },
      footers: { default: makeFooter() },
      children
    }]
  });
}


// ══════════════════════════════════════════════════════════════════════════════
// DOCUMENT 2 — RULES
// ══════════════════════════════════════════════════════════════════════════════
function buildRules() {
  const ruleRow = (num, title, detail, usedBy) => [
    new Paragraph({
      spacing: { before: 160, after: 40 },
      children: [
        new TextRun({ text: `Rule ${num}: `, bold: true, font: 'Arial', size: 22, color: '1F3864' }),
        new TextRun({ text: title, bold: true, font: 'Arial', size: 22 })
      ]
    }),
    new Paragraph({
      spacing: { after: 40 },
      children: [new TextRun({ text: detail, font: 'Arial', size: 21 })]
    }),
    new Paragraph({
      spacing: { after: 120 },
      children: [
        new TextRun({ text: 'Used by: ', bold: true, italics: true, font: 'Arial', size: 20, color: '2E75B6' }),
        new TextRun({ text: usedBy, italics: true, font: 'Arial', size: 20, color: '555555' })
      ]
    })
  ];

  const children = [
    ...coverPage(
      'RTA Monitor',
      'System Rules Reference — Master Rulebook',
      'June 2026', 'V3'
    ),

    h1('Introduction'),
    ruled(),
    body('This document lists every business rule, operational threshold, alert condition, chatbot formatting rule, and data integrity rule in the RTA Monitor system.'),
    ...spacer(1),
    body('The authoritative source for ALL rules is:', { bold: false }),
    new Paragraph({
      spacing: { after: 80 },
      shading: { fill: 'EEF4FF', type: ShadingType.CLEAR },
      children: [new TextRun({ text: '    prompts/rules.yaml', bold: true, font: 'Courier New', size: 22, color: '1F3864' })]
    }),
    ...spacer(1),
    body('To change any rule: edit rules.yaml only. No code changes required. The prompt_loader.py injects rules.yaml automatically into every LLM prompt at runtime.'),
    ...spacer(1),

    // ── Section 1 ─────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Section 1 — SLA Band Rules'),
    ruled(),
    body('These bands define what SLA% means in plain terms. Used by: Router (workflow.py), Agent 3 lever, Dashboard badge colour, Chatbot answer formatting.', { italics: true }),
    ...spacer(1),

    makeTable(
      ['Band', 'SLA Range', 'Badge Colour', 'Meaning'],
      [
        ['EXCELLENT', '95% and above',   'Blue',       'Ahead of target — no action needed'],
        ['HEALTHY',   '90% to 94.9%',    'Green',      'On target — monitor only'],
        ['WARNING',   '80% to 89.9%',    'Amber',      'Approaching breach — prepare agents'],
        ['CRITICAL',  '70% to 79.9%',    'Red/Orange', 'Active breach — escalate immediately'],
        ['SEVERE',    'Below 70%',        'Black',      'Crisis level — all levers must fire'],
      ],
      [1800, 1800, 1800, 3960]
    ),
    ...spacer(1),

    // ── Section 2 ─────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Section 2 — Lever Firing Rules'),
    ruled(),
    body('Used by: workflow.py router_node and Agent 3 (agent3_lever.py)', { italics: true }),
    ...spacer(1),

    ...ruleRow('2.1', 'Lever Thresholds',
      'Amber lever fires when SLA drops below 90%. Red lever fires when SLA drops below 80%. Black lever fires when SLA drops below 70%. Thresholds are configurable in config.json under agent3.amber_threshold, red_threshold, black_threshold.',
      'workflow.py, Agent 3'),

    ...ruleRow('2.2', 'One-Shot Rule',
      'Each lever (Amber, Red, Black) fires ONLY ONCE per SLA band crossing per skill. Once fired, it will not fire again until the skill fully recovers. Tracked per skill in LangGraph state as a3_fired_levers[skill_Amber], a3_fired_levers[skill_Red], a3_fired_levers[skill_Black].',
      'workflow.py router_node'),

    ...ruleRow('2.3', 'Recovery Rule',
      'A skill is considered RECOVERED when ALL three conditions are simultaneously true: (1) queue = 0, (2) avail > 0, (3) SLA >= 90%. On recovery: send a Teams RESOLVED message (green Adaptive Card) AND reset all fired levers for that skill so they can re-fire if SLA drops again.',
      'workflow.py _send_recovery_alerts()'),

    ...ruleRow('2.4', 'Progressive Escalation Rule',
      'If SLA drops from 85% to 65% in a single poll cycle, all three levers fire in the same cycle (assuming none were previously fired). Amber fires because SLA < 90%, Red fires because SLA < 80%, Black fires because SLA < 70%.',
      'workflow.py router_node'),

    // ── Section 3 ─────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Section 3 — Agent 2 Routing Rules'),
    ruled(),
    body('Used by: workflow.py router_node — determines whether Agent 2 (Analyst) is invoked.', { italics: true }),
    ...spacer(1),

    ...ruleRow('3.1', 'Queue Trigger',
      'Fire Agent 2 when queue >= queue_min AND avail = 0 for any skill. queue_min is configurable in config.json (agent2.queue_min, default = 1). This catches the moment calls are waiting with nobody available to answer.',
      'workflow.py router_node'),

    ...ruleRow('3.2', 'OCW Trigger (Oldest Call Waiting)',
      'Fire Agent 2 when OCW (Oldest Call Waiting in seconds) exceeds threshold AND queue > 0. OCW threshold is read per-skill first from config.json skill_thresholds[skill].ocw_threshold_sec, then falls back to global agent2.ocw_threshold_sec (default 60 seconds).',
      'workflow.py router_node, config_loader.get_ocw_threshold()'),

    ...ruleRow('3.3', 'LLM vs Rule-Based Flag',
      'Agent 2 uses LLM-generated recommendations ONLY when AUX agents exist (someone who can be moved to handle calls). If no agents are on AUX, Agent 2 uses a fast rule-based recommendation. This prevents wasting LLM tokens when no actionable recommendation is possible.',
      'workflow.py router_node (use_llm flag)'),

    ...ruleRow('3.4', 'Cooldown Rule',
      'Agent 2 will NOT alert the same skill twice within the cooldown window (default 300 seconds = 5 minutes). Tracked per skill in state as a2_last_alerted[skill] = timestamp. Prevents alert flooding for the same skill on every poll.',
      'agent2_analyst.py, config: agent2.cooldown_sec'),

    ...ruleRow('3.5', 'Systemic Crisis Rule',
      'If 3 or more skills in the same region are simultaneously in crisis (queue > 0 with avail = 0, or OCW breach), the router flags a SYSTEMIC CRISIS and logs a warning. Threshold configurable as SYSTEMIC_MIN_SKILLS = 3 in workflow.py.',
      'workflow.py router_node'),

    // ── Section 4 ─────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Section 4 — Agent 4 CMS Monitoring Rules'),
    ruled(),
    body('Used by: agents/agent4_cms_monitor.py — independent thread per region, every 60 seconds.', { italics: true }),
    ...spacer(1),

    ...ruleRow('4.1', 'AHT Breach Rule (Average Handle Time)',
      'Alert when any agent\'s current call duration exceeds their skill\'s AHT target by 10%. Formula: breach_threshold = aht_target_sec * 1.10. Per-skill target read from config.json skill_thresholds[skill].aht_target_min (converted to seconds). If per-skill = 0, fall back to global agent4.aht_target_min. If both = 0, AHT check is DISABLED. Alert shows top 3 longest calls plus overflow count.',
      'agent4_cms_monitor._analyse_aht(), config_loader.get_aht_target_sec()'),

    ...ruleRow('4.2', 'ACW Breach Rule (After-Call-Work)',
      'Alert when any agent stays in ACW state longer than acw_target_min (default 5 minutes). Setting acw_target_min = 0 disables the ACW check entirely for all skills. Agents sorted by longest ACW first in the Teams alert.',
      'agent4_cms_monitor._analyse_acw(), config: agent4.acw_target_min'),

    ...ruleRow('4.3', 'AUX Count Gate — Most Important Rule',
      'If the total number of agents currently on ANY AUX code is less than or equal to the skill\'s aux_threshold, ALL time-based AUX alerts are SUPPRESSED for that poll cycle. When total AUX count exceeds aux_threshold, normal per-code time checks fire. This prevents alert fatigue for healthy large teams (ProDB with 2 on break is fine) while catching real problems on struggling small teams (VICHW with 2 on AUX is a problem).',
      'agent4_cms_monitor._analyse_aux(), config_loader.get_aux_max()'),

    ...ruleRow('4.4', 'AUX Threshold Defaults by Pattern',
      'ProDB and ProCNX skills: aux_threshold = 3 (large healthy teams). VICHW and LicKeys skills: aux_threshold = 1 (consistently struggling or small teams). MLSCST skills: aux_threshold = 1 (small single-language EMEA teams). Elite and CritAcct: aux_threshold = 2. All others: aux_threshold = 2. Override per-skill in config.json skill_thresholds[skill].aux_threshold.',
      'core/config_loader.get_aux_max()'),

    h2('AUX Code Time Limits (Rule 4.5)'),
    body('After passing the AUX count gate, each AUX code is checked against its configured time limit. Configured in config.json agent4.aux_thresholds.', { italics: true }),
    ...spacer(1),
    makeTable(
      ['AUX Code', 'Name', 'Max Time (min)', 'Enabled by Default'],
      [
        ['AUX1', 'IT Issue',    '0',   'No (disabled)'],
        ['AUX2', 'Break',       '15',  'Yes'],
        ['AUX3', 'Lunch',       '30',  'Yes'],
        ['AUX4', 'Coaching',    '20',  'Yes'],
        ['AUX5', 'Case Mgmt',   '20',  'Yes'],
        ['AUX6', 'Meeting',     '60',  'Yes'],
        ['AUX7', 'Training',    '120', 'Yes'],
        ['AUX8', 'Unavailable', '10',  'Yes'],
        ['AUX9', 'Offline',     '5',   'Yes'],
      ],
      [2000, 2000, 2000, 2360]
    ),
    ...spacer(1),

    ...ruleRow('4.6', 'Stagger Rule',
      'Agent 4 threads start staggered to prevent all 10 regions firing Teams alerts simultaneously on startup. Start delay = region_index × 6 seconds. Region 0 starts at 0s, Region 9 starts at 54s.',
      'run_all.py, agent4_monitor_loop(initial_delay_sec)'),

    ...ruleRow('4.7', 'Skip Inactive Skills Rule',
      'If skill_thresholds[skill].active = false in config.json, Agent 4 skips that skill entirely for all checks (AHT, AUX, ACW). Useful for skills that are temporarily offline or not yet staffed.',
      'agent4_cms_monitor.agent4_monitor()'),

    // ── Section 5 ─────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Section 5 — Data Integrity Rules'),
    ruled(),
    body('Used by: run_all.py and agents/agent4_cms_monitor.py for all file write operations.', { italics: true }),
    ...spacer(1),

    ...ruleRow('5.1', 'Atomic Write Rule',
      'All writes to live_state.json and cms_agents.json use write-to-tmp-then-rename: (1) write to file.tmp, (2) os.replace(file.tmp, file) — atomic rename. If rename fails (OneDrive sync lock), retry up to 3 times with 0.1 second sleep. Final fallback: direct write. Prevents partial writes if the process is interrupted.',
      'run_all.py _update_live_state(), agent4_cms_monitor._save_agents_snapshot()'),

    ...ruleRow('5.2', 'Shared Cross-Region Lock Rule',
      'cms_agents.json is written by 10 region threads simultaneously. A single threading.Lock() stored in sys.modules under key __rta_cms_agents_lock__ is shared across all region module copies. Without this, a plain class-level lock would NOT be shared between separately-loaded module instances.',
      'agent4_cms_monitor.py (_CMS_STATE_LOCK via sys.modules)'),

    ...ruleRow('5.3', 'SQLite WAL Mode Rule',
      'history.db uses WAL (Write-Ahead Log) mode. This allows concurrent reads during writes — critical for chatbot queries running while 10 region threads insert simultaneously. Never switch to journal mode or use check_same_thread=False workarounds.',
      'core/history.py _init_db()'),

    ...ruleRow('5.4', 'Data Retention Rule',
      'history.db retains data for 7 days rolling. Cleanup (DELETE WHERE timestamp older than 7 days) runs at most once per hour per process. Recommend PostgreSQL migration if retention needs exceed 30 days.',
      'core/history.py cleanup_old_data()'),

    // ── Section 6 ─────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Section 6 — LLM Usage Rules'),
    ruled(),
    body('Used by: core/llm.py, workflow.py, app.py', { italics: true }),
    ...spacer(1),

    ...ruleRow('6.1', 'Provider Priority Rule',
      'NVIDIA NIM (meta/llama-3.1-70b-instruct) is the primary provider for best quality lever analysis. Groq (llama3-70b-8192) is the first fallback for fast response. Gemini (gemini-1.5-flash) is the secondary fallback.',
      'core/llm.py call_llm()'),

    ...ruleRow('6.2', 'Key Rotation Rule',
      'API keys rotate round-robin across all keys in the pool. On 429 (rate limit): rotate to next key and apply exponential backoff up to a maximum of 30 seconds. Total retry attempts = 2 times the pool size.',
      'core/llm.py call_llm()'),

    ...ruleRow('6.3', 'Temperature Rule',
      'Always use temperature = 0.3. Low temperature produces deterministic, consistent outputs for lever analysis and analyst recommendations. Do not increase without testing for output variability.',
      'core/llm.py (_call_nvidia, _call_groq, _call_gemini)'),

    ...ruleRow('6.4', 'Per-Region Lock Rule',
      'Only one LLM call per region at a time. Per-region threading.Lock() ensures A2 and chatbot calls from the same region queue — never run in parallel. Prevents race conditions on region state.',
      'core/llm.py (per-region lock via sys.modules key)'),

    ...ruleRow('6.5', 'LLM Invoke Condition',
      'Agent 2 only invokes the LLM when AUX agents exist to move. If no agents are on AUX, Agent 2 falls back to a rule-based recommendation with no LLM cost or latency.',
      'workflow.py router_node (use_llm flag), agent2_analyst.py'),

    // ── Section 7 ─────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Section 7 — Chatbot SQL Generation Rules'),
    ruled(),
    body('Used by: prompts/chatbot_sql_gen.txt — injected into LLM when generating SQL for history queries.', { italics: true }),
    ...spacer(1),

    ...ruleRow('7.1', 'SQL Safety Rule',
      'Only SELECT statements are allowed. Any DROP, UPDATE, INSERT, or DELETE statement raises an error before execution. Maximum 500 rows returned from any query. Date constraint is injected server-side by Python — LLM must copy verbatim, never recalculate dates.',
      'app.py /api/chat history mode'),

    ...ruleRow('7.2', 'Table Routing Rule',
      'SLA, band, queue, OCW, lever, breach, root_cause questions → query skill_history table. Agent names, AUX reasons, who is on break, time in state → query cms_history table. Never mix columns from different tables in the same query.',
      'chatbot_sql_gen.txt'),

    ...ruleRow('7.3', 'Region Tag Mapping Rule',
      'India/IND → rta. China/CHN → cn. Australia/AUS → au. EMEA/Europe → emea. Hong Kong/HK → hk. Malaysia/MY → my. Korea/KOR → kr. Thailand/TH → th. Brazil/BR → br. Taiwan/TW → tw. Never guess a region tag. Always use exact tags from this mapping.',
      'chatbot_sql_gen.txt'),

    ...ruleRow('7.4', 'Time Conversion Rule',
      'All timestamps stored in 24-hour format. Business hours 1–8 without am/pm = PM (add 12): 4:50 → 16:50. Hours 9–12 without am/pm = AM: 9:00 → 09:00. For "at HH:MM": use strftime(\'%H:%M\', timestamp) BETWEEN \'HH:MM-2min\' AND \'HH:MM+2min\'.',
      'chatbot_sql_gen.txt'),

    ...ruleRow('7.5', 'Worst Skill Query Rule',
      'For worst/most impacted/lowest SLA: use ORDER BY sla ASC LIMIT N. NEVER use sla < (SELECT MIN(sla)...) — this always returns 0 rows because nothing is less than the minimum. NEVER use sla = (SELECT MIN(sla)...) with subquery on large datasets.',
      'chatbot_sql_gen.txt'),

    h2('Query Limit Rules (Rule 7.6)'),
    makeTable(
      ['Query Type', 'LIMIT', 'When to Use'],
      [
        ['Single point (at a specific time)', 'LIMIT 5', '"at 4:50 PM", "at 3 PM"'],
        ['Range or full day', 'LIMIT 60', '"yesterday", "today", "past N hours"'],
        ['Worst skill (no time range)', 'LIMIT 6', '"worst skill", "lowest SLA"'],
        ['Default (unclear)', 'LIMIT 20', 'Any other query type'],
      ],
      [3200, 1500, 3660]
    ),
    ...spacer(1),

    // ── Section 8 ─────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Section 8 — Chatbot Answer Rules'),
    ruled(),
    body('Used by: prompts/chatbot_answer.txt — injected via {rules} placeholder on every chatbot answer.', { italics: true }),
    ...spacer(1),

    ...ruleRow('8.1', 'Anti-Hallucination Rule',
      'Only use facts from the context provided. If context says "No data found", reply with that only — never invent SLA values, agent names, lever fires, or timestamps. This is the most important rule.',
      'chatbot_answer.txt, rules.yaml general_rules'),

    ...ruleRow('8.2', 'Region Name Rule',
      'Always use full region names in answers (India, Hong Kong, Australia). Never use raw tags (rta, hk, au). The reader should not see internal system identifiers.',
      'rules.yaml general_rules'),

    ...ruleRow('8.3', 'Timestamp Conversion Rule',
      'Convert all raw timestamps to 12-hour format in answers. "2026-06-09 16:45:00" becomes "4:45 PM". Never show raw database timestamp format to the user.',
      'rules.yaml general_rules'),

    ...ruleRow('8.4', 'Formatting Rules',
      'Bold all key metrics, skill names, agent names, lever colours, and band names. Never dump raw dicts, column names, or unformatted numbers. No padding or filler introductory sentences — start directly with the answer.',
      'rules.yaml general_rules'),

    ...ruleRow('8.5', 'Range Query Rule',
      'For full-day or range questions, use ALL rows in the context — not just a sample. The aggregation has already been done; the LLM must use every data point provided.',
      'rules.yaml general_rules'),

    ...ruleRow('8.6', 'No-Lever Confirmation Rule',
      'If no lever fired in the period, explicitly state: "✅ No lever fires recorded." This tells the reader the check was performed and found nothing — not that it was skipped.',
      'rules.yaml general_rules'),

    ...ruleRow('8.7', 'Agent Name Guard Rule',
      'If cms_agents.json is not yet loaded, show count only. Guard message: "⚠ Individual agent names NOT available — CMS data not yet loaded. Show count only." Never show an empty agent table. Never invent agent names.',
      'rules.yaml anti_hallucination_agent_names'),

    // ── Section 9 ─────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Section 9 — Chatbot Output Format Rules'),
    ruled(),
    body('These rules define exactly how each type of question should be formatted in the chatbot answer. Defined in rules.yaml output_formats. Applied by the LLM.', { italics: true }),
    ...spacer(1),

    makeTable(
      ['Query Type', 'Trigger Keywords', 'Format'],
      [
        ['Current Status',      '"current status", "SLA now", "live overview"',          'Markdown table: Region | Skill | SLA | Band | Queue | Avail | Lever. One-line summary at end.'],
        ['Single Point',        '"at 4:50 PM", "SLA of ProDB at 3 PM"',                 '3-4 bullets: Skill, Region, SLA with band emoji, Queue/Available, Lever status.'],
        ['Range / Full Day',    '"yesterday", "last day", "performance last hour"',      'Scorecard table + Time in Band line + 2-3 sentence narrative.'],
        ['Improvement Actions', '"how to improve", "recommendations", "what to do"',     'Per-skill block: Immediate (5-10 min) + Short-term (30 min). Named agents. Sort SEVERE to WARNING.'],
        ['Worst Impacted',      '"which is worst", "most critical region"',              'One sentence + 3 bullets: SLA, Queue/OCW, Lever.'],
        ['Agent AUX',           '"who is on AUX", "agents on break"',                   'No AUX: single line. With names: table. Without names: counts per skill only.'],
        ['Lever',               '"what levers fired", "any escalations"',               'Table sorted by time: Time | Region | Skill | Lever | Action.'],
        ['Comparison',          '"compare India vs China", "which region is worst"',    'Side-by-side table: Avg SLA, Band, Breached skills, Levers fired.'],
        ['Trend',               '"is SLA improving", "when did things get bad"',        'Timeline table: Time | SLA | Band | Event. Narrative above.'],
      ],
      [1800, 2500, 4060]
    ),
    ...spacer(2),

    // ── Summary ───────────────────────────────────────────────────────────────
    pageBreak(),
    h1('Rules Summary — Where Each Rule Lives'),
    ruled(),
    makeTable(
      ['Rule Section', 'Count', 'Source File', 'Stage'],
      [
        ['SLA Band Definitions',       '5 bands',  'rules.yaml Section 2',  'Router, Dashboard, Chatbot'],
        ['Lever Firing Rules',         '4 rules',  'rules.yaml Section 3',  'workflow.py, Agent 3'],
        ['Agent 2 Routing Rules',      '5 rules',  'rules.yaml Section 4',  'workflow.py router_node'],
        ['Agent 4 CMS Rules',          '7 rules',  'rules.yaml Section 5',  'agent4_cms_monitor.py'],
        ['Data Integrity Rules',       '4 rules',  'rules.yaml Section 6',  'run_all.py, agent4'],
        ['LLM Usage Rules',            '5 rules',  'rules.yaml Section 7',  'core/llm.py'],
        ['SQL Generation Rules',       '6 rules',  'rules.yaml Section 8',  'chatbot_sql_gen.txt'],
        ['Chatbot Answer Rules',       '7 rules',  'rules.yaml Section 9',  'chatbot_answer.txt'],
        ['Output Format Rules',        '9 formats','rules.yaml Section 10', 'LLM answer generation'],
      ],
      [2800, 1200, 2300, 3060]
    ),
  ];

  return new Document({
    styles: STYLES,
    numbering: NUMBERING,
    sections: [{
      properties: SECTION_PROPS,
      headers: { default: makeHeader('RTA Monitor — System Rules Reference') },
      footers: { default: makeFooter() },
      children
    }]
  });
}

// ── Write both docs ───────────────────────────────────────────────────────────
async function main() {
  const featDoc = buildFeatures();
  const rulesDoc = buildRules();

  const featBuf  = await Packer.toBuffer(featDoc);
  const rulesBuf = await Packer.toBuffer(rulesDoc);

  const featPath  = path.join(OUT, 'RTA_Features.docx');
  const rulesPath = path.join(OUT, 'RTA_Rules.docx');

  fs.writeFileSync(featPath, featBuf);
  fs.writeFileSync(rulesPath, rulesBuf);

  console.log('Created:', featPath);
  console.log('Created:', rulesPath);
}

main().catch(e => { console.error(e); process.exit(1); });
