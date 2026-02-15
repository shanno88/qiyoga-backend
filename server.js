require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');

const multer = require('multer');
const upload = multer({ dest: 'uploads/' });
const Tesseract = require('tesseract.js');
const OpenAI = require('openai');
const fs = require('fs');
const pdfParse = require('pdf-parse');
const sharp = require('sharp');
const { v4: uuidv4 } = require('uuid');

const deepseek = new OpenAI({
  apiKey: process.env.DEEPSEEK_API_KEY,
  baseURL: 'https://api.deepseek.com/v1'
});

const CLAUSE_EXPLAINER_SYSTEM_PROMPT = `You are a contract explainer for Chinese international students.

Right now, there is a BUG in how you respond:

Sometimes you only output English.

Sometimes you only output Chinese.

But the user ALWAYS needs a pair:

one line with the original English clause,

one line with a Chinese explanation starting with "中文解释："。

Your job is to FIX this behavior in ALL your future answers for this chat.

From now on, for every user input with English rental clauses:

For EACH clause, you MUST output exactly two lines:

Line 1: the original English clause in ONE line (copy the user's English text, do NOT change words, do NOT summarize, do NOT translate).

Line 2: a Chinese explanation starting with "中文解释：", using 1–2 short sentences of natural, easy Chinese to explain what the clause means for the tenant (what they must do, deadlines, money rules, consequences).

Between different clauses, leave EXACTLY ONE blank line.

You MUST NOT:

add titles, headings, bullet points, section names, or numbers other than those already in the original English text;

output any extra English explanation besides line 1;

answer only in English or only in Chinese;

change this format unless the system prompt in this conversation is changed.

Think step by step BEFORE you answer:

First, split the user's input into clauses (each paragraph starting with something like "THIS AGREEMENT…", "1.", "2.", "RENT:", "5. RENT DUE DATE:", etc.).

Then, for each clause:

copy that whole clause into one single English line;

generate one Chinese explanation line starting with "中文解释："。

Your final output to the user MUST ONLY be:

[English clause line 1]
中文解释：[Chinese explanation line 1]

[English clause line 2]
中文解释：[Chinese explanation line 2]

[English clause line 3]
中文解释：[Chinese explanation line 3]

…and so on.`;

const BILINGUAL_EXPLAINER_SYSTEM_PROMPT = `You are a rental agreement explainer for Chinese international students in the US.

YOUR TASK
Convert any English lease-related text into a bilingual two-line format.

IMPORTANT
The English text you receive may be:
- an original lease clause, OR
- an English analysis, suggestion, or recommendation (e.g. "Negotiate pet fee waiver or one-time $200 instead of monthly", "Save ~$100/year").

In ALL cases, you must treat each English line as content to be bilingualized.

OUTPUT FORMAT (STRICT – NO DEVIATIONS)

For each English line you receive in the user message, output exactly two lines:

- Line 1: Copy the English text EXACTLY as provided in the input.
- Line 2: Start with "中文解释：" and then write 1–3 sentences of natural Chinese explaining:
  - what that English line means,
  - what the tenant should do or understand,
  - and, if relevant, the money impact or risk.

Put ONE blank line between different English lines.

RULES
1. Line 1 = always copy the English input line exactly. Never modify it.
2. Line 2 = always start with "中文解释：" and be written mainly in Chinese.
3. Do not add extra titles, emojis, or bullet points.
4. For multiple lines in one message, output repeated blocks:

[original English line]
中文解释：[Chinese explanation]

separated by one blank line.

RESPONSE BEHAVIOR
- As soon as you receive English text, immediately output the two-line blocks.
- Do not reply with "Understood" or "Ready".`;

function parseBilingualResponse(responseText) {
  const clauses = [];
  const blocks = responseText.split(/\n\n+/).filter(block => block.trim());
  
  for (const block of blocks) {
    const lines = block.split('\n').filter(line => line.trim());
    if (lines.length >= 2) {
      const englishLine = lines[0].trim();
      const chineseLine = lines.find(l => l.startsWith('中文解释：'));
      
      if (chineseLine) {
        clauses.push({
          clause_text: englishLine,
          chinese_explanation: chineseLine.replace('中文解释：', '').trim()
        });
      }
    }
  }
  
  return clauses;
}

async function getChineseExplanation(englishText) {
  console.log('🤖 [AI] Getting Chinese explanation...');
  
  try {
    const response = await deepseek.chat.completions.create({
      model: 'deepseek-chat',
      messages: [
        { role: 'system', content: BILINGUAL_EXPLAINER_SYSTEM_PROMPT },
        { role: 'user', content: englishText }
      ],
      temperature: 0.3,
      max_tokens: 1000
    });
    
    const result = response.choices[0]?.message?.content || '';
    const parsed = parseBilingualResponse(result);
    
    if (parsed.length > 0) {
      return parsed[0].chinese_explanation;
    }
    return null;
  } catch (error) {
    console.error('❌ [AI] DeepSeek error in getChineseExplanation:', error.message);
    return null;
  }
}

async function analyzeClausesWithAI(clausesText, language = 'zh') {
  if (language !== 'zh') {
    return null;
  }
  
  console.log('🤖 [AI] Analyzing clauses with DeepSeek...');
  console.log('🤖 [AI] Input length:', clausesText.length, 'characters');
  
  try {
    const response = await deepseek.chat.completions.create({
      model: 'deepseek-chat',
      messages: [
        { role: 'system', content: CLAUSE_EXPLAINER_SYSTEM_PROMPT },
        { role: 'user', content: clausesText }
      ],
      temperature: 0.3,
      max_tokens: 4000
    });
    
    const result = response.choices[0]?.message?.content || '';
    console.log('🤖 [AI] Response length:', result.length, 'characters');
    console.log('🤖 [AI] Response preview:', result.substring(0, 200));
    
    return result;
  } catch (error) {
    console.error('❌ [AI] DeepSeek error:', error.message);
    return null;
  }
}

const paddleVerify = require('./middleware/paddleVerify');
const db = require('./database');

// 定义数据库路径
const dbPath = process.env.DB_PATH || path.join(__dirname, 'database.sqlite');
console.log('📊 Database path:', dbPath);

const app = express();

const PORT = process.env.PORT || 3001;
const ALLOWED_ORIGINS = process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:5173', 'http://localhost:3000'];

app.use(cors({
  origin: ALLOWED_ORIGINS,
  credentials: true
}));

app.use(express.json());

app.use(express.urlencoded({ extended: true }));

app.get('/', (req, res) => {
  res.json({
    service: 'QiYoga Backend',
    version: '1.0.0',
    endpoints: {
      health: '/health',
      webhook: '/webhook/paddle',
      ocr: '/api/lease/analyze'
    }
  });
});

app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    message: 'QiYoga Backend is running',
    timestamp: new Date().toISOString()
  });
});

app.post('/webhook/paddle', paddleVerify, async (req, res) => {
  const event = req.body;
  console.log('\n=== WEBHOOK RECEIVED ===');
  console.log('Event ID:', event.event_id);
  console.log('Event Type:', event.event_type);

  try {
    if (event.event_type === 'transaction.completed' || event.event_type === 'payment.succeeded') {
      const data = event.data;
      console.log('💰 Payment/Transaction succeeded!');
      console.log('Transaction ID:', data.id);
      console.log('Customer ID:', data.customer_id);
      console.log('Amount:', data.amount);
      console.log('Currency:', data.currency);
      console.log('Customer Email:', data.customer?.email);
      console.log('Custom Data:', data.custom_data);

      // Store transaction in database
      db.run(`
        INSERT INTO transactions (transaction_id, customer_id, customer_email, amount, currency, custom_data, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'succeeded', CURRENT_TIMESTAMP)
      `, [data.id, data.customer_id, data.customer?.email, data.amount, data.currency, JSON.stringify(data.custom_data)]);

      // Check and grant user access
      if (data.customer?.email) {
        const hasAccess = await db.hasUserAccess(data.customer.email);
        if (!hasAccess) {
          db.grantUserAccess(data.customer.email, data.custom_data?.user_id);
          console.log('✅ Granted 30-day access to user:', data.customer.email);
        } else {
          console.log('ℹ️  User already has access:', data.customer.email);
        }
      }

      const transactionRecord = {
        transaction_id: data.id,
        customer_id: data.customer_id,
        customer_email: data.customer?.email,
        amount: data.amount,
        currency: data.currency,
        custom_data: data.custom_data,
        status: 'succeeded',
        timestamp: new Date().toISOString()
      };

      console.log('💾 Transaction record:', JSON.stringify(transactionRecord, null, 2));
    } else {
      console.log('ℹ️  Received event:', event.event_type);
    }

    res.status(200).json({ received: true });
    console.log('=== WEBHOOK PROCESSING COMPLETE ===\n');
  } catch (error) {
    console.error('❌ Error processing webhook:', error);
    res.status(500).json({ error: 'Failed to process webhook', details: error.message });
  }
});

app.post('/api/ocr', upload.single('file'), async (req, res) => {
  console.log('\n' + '='.repeat(60));
  console.log('📄 OCR REQUEST RECEIVED');
  console.log('='.repeat(60));
  
  console.log('🔍 RAW req.body:', JSON.stringify(req.body, null, 2));
  console.log('📄 req.file:', req.file?.originalname);
  console.log('🌐 ALL FORM FIELDS:', Object.keys(req.body));
  console.log('📊 language param:', req.body?.language);
  
  console.log('   📁 Filename:', req.file?.originalname || 'N/A');
  console.log('   📦 Size:', req.file ? `${(req.file.size / 1024).toFixed(1)}KB` : 'N/A');
  console.log('   📝 MIME Type:', req.file?.mimetype || 'N/A');
  console.log('   🆔 Temp Path:', req.file?.path || 'N/A');
  console.log('   ⏰ Timestamp:', new Date().toISOString());
  
  const forceEnglish = req.body?.test === 'true' || 
                       req.query?.debug === 'en' || 
                       req.body?.language === 'en';
  
  console.log('🧪 FORCE ENGLISH?', forceEnglish);
  console.log('🧪 [DEBUG] req.body.test:', req.body?.test);
  console.log('🧪 [DEBUG] req.query.debug:', req.query?.debug);
  console.log('🧪 [DEBUG] req.body.language:', req.body?.language);
  
  const language = forceEnglish ? 'en' : 'zh';
  console.log('🎯 FINAL LANGUAGE:', language);
  
  if (!req.file) {
    console.log('❌ ERROR: No file uploaded');
    return res.status(400).json({ success: false, error: 'No file uploaded' });
  }
  const analysisId = 'demo_' + Date.now().toString(36);
  const startTime = Date.now();
  console.log('   🎯 Analysis ID:', analysisId);
  console.log('   🚀 Starting demo analysis...');
  try {
    if (req.file?.path && fs.existsSync(req.file.path)) {
      fs.unlinkSync(req.file.path);
      console.log('   🗑️  Temp file cleaned up');
    }
    const processingTime = ((Date.now() - startTime) / 1000).toFixed(1);
    console.log(`\n📊 [DEBUG] Language requested: ${language}`);
    if (forceEnglish) {
      console.log('✅ 发送英文数据');
    } else {
      console.log('✅ 发送中文数据');
    }
    console.log('📤 [DEBUG] Returning response in: ' + (language === 'en' ? 'English' : 'Chinese'));
    console.log('='.repeat(60) + '\n');
    
    const isEnglish = forceEnglish;
    
    res.json({
      success: true,
      data: {
        analysis_id: analysisId,
        has_full_access: true,
        risk_score: 76,
        risk_level: isEnglish ? 'Medium' : '中',
        pages: 3,
        processing_time: processingTime + 's',
        key_info: {
          landlord: 'ABC Properties LLC',
          landlord_contact: '123 Main St, Los Angeles, CA 90001',
          tenant: 'Silvia Mando',
          tenant_contact: isEnglish ? 'Contact phone provided' : '提供的联系电话',
          address: '9876 Cherry Ave, Apt 426, Los Angeles, CA 90001',
          property_type: isEnglish ? 'Residential Apartment' : '住宅公寓',
          rent: isEnglish ? '$685/month' : '$685/月',
          rent_due_date: isEnglish ? '1st of each month' : '每月1日',
          deposit: '$685',
          deposit_refund: isEnglish ? 'Refunded within 30 days after lease ends' : '租约结束后30天内退还',
          term: isEnglish ? '12 months' : '12个月',
          start_date: isEnglish ? 'March 1, 2024' : '2024年3月1日',
          end_date: isEnglish ? 'February 28, 2025' : '2025年2月28日',
          square_feet: isEnglish ? 'Approx. 650 sq ft' : '约650平方英尺',
          bedrooms: '1',
          bathrooms: '1'
        },
        red_flags: isEnglish ? [
          {
            id: 1,
            severity: 'high',
            clause: 'Clause 5 - Late Fee',
            issue: 'Late fee $25 + $5/day is excessive, may accumulate to high penalties',
            impact: '10 days late = $75 penalty, 11% of monthly rent'
          },
          {
            id: 2,
            severity: 'medium',
            clause: 'Clause 7 - Security Deposit',
            issue: 'Security deposit $685 earns no interest, tenant loses potential earnings',
            impact: 'At 2% annual rate, ~$13.70 lost per year'
          },
          {
            id: 3,
            severity: 'high',
            clause: 'Clause 12 - Cleaning Fee',
            issue: '$200 cleaning fee standard is vague, no clear inspection checklist',
            impact: 'Full deposit could be deducted'
          },
          {
            id: 4,
            severity: 'medium',
            clause: 'Clause 9 - Pet Policy',
            issue: 'Pets require extra $25/month + $300 non-refundable deposit',
            impact: 'Additional $600/year, 30% increase in housing cost'
          },
          {
            id: 5,
            severity: 'high',
            clause: 'Clause 15 - Early Termination',
            issue: 'Early termination requires 2 months rent as penalty',
            impact: 'Maximum loss of $1,370'
          },
          {
            id: 6,
            severity: 'medium',
            clause: 'Clause 8 - Maintenance Responsibility',
            issue: 'Delayed reporting may result in tenant bearing repair costs',
            impact: 'Uncontrollable potential repair expenses'
          },
          {
            id: 7,
            severity: 'low',
            clause: 'Clause 14 - Guest Policy',
            issue: 'Guests staying over 14 days require written approval',
            impact: 'May affect short-term visits from family and friends'
          },
          {
            id: 8,
            severity: 'medium',
            clause: 'Clause 18 - Landlord Entry Rights',
            issue: 'Landlord may enter with 24-hour notice for inspection',
            impact: 'Privacy limited, must accommodate landlord schedule'
          }
        ] : [
          {
            id: 1,
            severity: 'high',
            clause: '第5条 - 迟交费条款',
            issue: '迟交费$25 + $5/天过高，可能累计造成高额罚金',
            impact: '若延迟10天，罚金可达$75，占月租11%'
          },
          {
            id: 2,
            severity: 'medium',
            clause: '第7条 - 押金条款',
            issue: '押金$685无利息支付，租户损失潜在收益',
            impact: '按2%年利率计算，一年损失约$13.70'
          },
          {
            id: 3,
            severity: 'high',
            clause: '第12条 - 清洁费条款',
            issue: '清洁费$200标准模糊，缺乏明确验收清单',
            impact: '可能被全额扣除押金'
          },
          {
            id: 4,
            severity: 'medium',
            clause: '第9条 - 宠物条款',
            issue: '宠物需额外$25/月 + $300不可退还押金',
            impact: '一年额外成本$600，增加30%租房开支'
          },
          {
            id: 5,
            severity: 'high',
            clause: '第15条 - 提前解约条款',
            issue: '提前解约需支付2个月租金作为违约金',
            impact: '最高损失$1,370'
          },
          {
            id: 6,
            severity: 'medium',
            clause: '第8条 - 维修责任条款',
            issue: '延迟报告问题可能导致租户承担维修责任',
            impact: '潜在维修费用不可控'
          },
          {
            id: 7,
            severity: 'low',
            clause: '第14条 - 访客条款',
            issue: '访客停留超过14天需书面批准',
            impact: '可能影响家人朋友短期探访'
          },
          {
            id: 8,
            severity: 'medium',
            clause: '第18条 - 房东进入权条款',
            issue: '房东可提前24小时通知进入检查',
            impact: '隐私权受限，需配合房东时间'
          }
        ],
        negotiation_tips: isEnglish ? [
          {
            id: 1,
            priority: 'high',
            category: 'Fee Negotiation',
            tip: 'Negotiate fixed late fee of $15, remove daily accumulation clause',
            expected_savings: 'Potential savings of $60 per late payment'
          },
          {
            id: 2,
            priority: 'high',
            category: 'Deposit Rights',
            tip: 'Request 2% annual interest on security deposit',
            expected_savings: 'Earn $13.70/year in interest'
          },
          {
            id: 3,
            priority: 'high',
            category: 'Fee Clarity',
            tip: 'Define cleaning standards and inspection checklist, take photos',
            expected_savings: 'Protect $685 deposit from improper deductions'
          },
          {
            id: 4,
            priority: 'medium',
            category: 'Pet Fees',
            tip: 'Negotiate pet fee waiver or one-time $200 instead of monthly',
            expected_savings: 'Save ~$100/year'
          },
          {
            id: 5,
            priority: 'high',
            category: 'Termination Penalty',
            tip: 'Reduce penalty to 1 month rent, add 30-day buffer period',
            expected_savings: 'Reduce potential loss by $685'
          },
          {
            id: 6,
            priority: 'medium',
            category: 'Privacy Protection',
            tip: 'Require 48-hour notice for landlord entry, tenant must be present',
            expected_savings: 'Protect residential privacy rights'
          }
        ] : [
          {
            id: 1,
            priority: 'high',
            category: '费用谈判',
            tip: '谈判固定迟交费$15，取消每日累加条款',
            expected_savings: '潜在节省$60/次逾期'
          },
          {
            id: 2,
            priority: 'high',
            category: '押金权益',
            tip: '要求押金按年2%计息，合理保障权益',
            expected_savings: '获得$13.70/年利息'
          },
          {
            id: 3,
            priority: 'high',
            category: '费用明确',
            tip: '明确清洁标准和验收清单，拍照留证',
            expected_savings: '保护$685押金不被不当扣除'
          },
          {
            id: 4,
            priority: 'medium',
            category: '宠物费用',
            tip: '协商宠物费用减免或一次性支付$200替代月付',
            expected_savings: '节省约$100/年'
          },
          {
            id: 5,
            priority: 'high',
            category: '违约金',
            tip: '降低违约金至1个月租金，增加30天缓冲期',
            expected_savings: '减少$685潜在损失'
          },
          {
            id: 6,
            priority: 'medium',
            category: '隐私保护',
            tip: '要求房东进入需48小时通知，且租户在场',
            expected_savings: '保护居住隐私权'
          }
        ],
        clause_summary: isEnglish ? {
          rent: {
            clause_number: 'Clause 2',
            title: 'Rent Payment',
            summary: '$685 due on 1st of each month, 3-day grace period, $25+$5/day late fee from day 4',
            details: 'Accepts check, bank transfer, no cash'
          },
          utilities: {
            clause_number: 'Clause 3',
            title: 'Utilities',
            summary: 'Tenant pays electricity, gas, phone, internet, and trash',
            details: 'Landlord covers water and sewage'
          },
          deposit: {
            clause_number: 'Clause 7',
            title: 'Security Deposit',
            summary: '$685 deposit, refunded within 30 days after lease ends, no interest',
            details: 'May deduct unpaid rent, damage repairs, cleaning fees'
          },
          late_fee: {
            clause_number: 'Clause 5',
            title: 'Late Fee',
            summary: 'Base $25 + $5/day accumulated, max $100',
            details: 'Over 15 days unpaid may trigger eviction'
          },
          maintenance: {
            clause_number: 'Clause 8',
            title: 'Maintenance Responsibility',
            summary: 'Must immediately report leaks, termites, appliance issues',
            details: 'Delayed reporting may result in tenant bearing repair costs'
          },
          termination: {
            clause_number: 'Clause 15',
            title: 'Early Termination',
            summary: '30-day written notice required, 2 months rent penalty',
            details: 'Penalty may be deducted from deposit'
          },
          pets: {
            clause_number: 'Clause 9',
            title: 'Pet Policy',
            summary: 'Small pets allowed (≤25 lbs), $25/month + $300 deposit',
            details: 'Vaccination records required, no dangerous breeds'
          },
          guests: {
            clause_number: 'Clause 14',
            title: 'Guest Policy',
            summary: 'Guests may stay 14 days, longer requires written approval',
            details: 'Unapproved extended stay considered breach'
          },
          entry_rights: {
            clause_number: 'Clause 18',
            title: 'Landlord Entry Rights',
            summary: 'Landlord may enter with 24-hour notice for inspection/repair',
            details: 'Emergency entry allowed immediately'
          },
          insurance: {
            clause_number: 'Clause 11',
            title: 'Insurance Requirement',
            summary: 'Renters insurance recommended, coverage ≥$10,000',
            details: 'Landlord not liable for tenant property loss'
          }
        } : {
          rent: {
            clause_number: '第2条',
            title: '租金支付',
            summary: '每月1日支付$685，3天宽限期，第4天起计迟交费$25+$5/天',
            details: '接受支票、银行转账，不接受现金'
          },
          utilities: {
            clause_number: '第3条',
            title: '公用事业',
            summary: '租户承担电、气、电话、网络及垃圾处理费用',
            details: '房东承担水费和污水处理费'
          },
          deposit: {
            clause_number: '第7条',
            title: '押金',
            summary: '押金$685，租约结束后30天内退还，无利息',
            details: '可扣除未付租金、损坏维修、清洁费'
          },
          late_fee: {
            clause_number: '第5条',
            title: '迟交费',
            summary: '逾期$25基础费 + $5/天累加，上限$100',
            details: '超过15天未付可启动驱逐程序'
          },
          maintenance: {
            clause_number: '第8条',
            title: '维护责任',
            summary: '需立即报告漏水、白蚁、电器故障等问题',
            details: '延迟报告可能导致租户承担维修费用'
          },
          termination: {
            clause_number: '第15条',
            title: '提前解约',
            summary: '需提前30天书面通知，支付2个月租金违约金',
            details: '违约金可从押金中扣除'
          },
          pets: {
            clause_number: '第9条',
            title: '宠物政策',
            summary: '允许小型宠物(≤25磅)，需$25/月 + $300押金',
            details: '需提供疫苗证明，禁止危险品种'
          },
          guests: {
            clause_number: '第14条',
            title: '访客规定',
            summary: '访客可停留14天，超期需书面批准',
            details: '未经批准超期视为违约'
          },
          entry_rights: {
            clause_number: '第18条',
            title: '房东进入权',
            summary: '房东可提前24小时通知进入检查、维修',
            details: '紧急情况可立即进入'
          },
          insurance: {
            clause_number: '第11条',
            title: '保险要求',
            summary: '建议租户购买 renters insurance，保额≥$10,000',
            details: '房东不承担租户财产损失'
          }
        }
      }
    });
  } catch (error) {
    console.error('❌ OCR ERROR:', error.message);
    console.error('   Stack:', error.stack);
    res.status(500).json({
      success: false,
      error: 'Analysis failed',
      details: error.message
    });
  }
});

app.post('/api/lease/analyze', upload.single('file'), async (req, res) => {
  res.status(200).json({
    success: false,
    error: 'This Node.js endpoint has moved. Please use /api/ocr or deploy the FastAPI backend for /api/lease/analyze',
    hint: 'The deployed backend is Node.js. For /api/lease/analyze, deploy app.py (FastAPI) instead.'
  });
});

app.post('/api/analyze-clauses', express.json(), async (req, res) => {
  console.log('\n' + '='.repeat(60));
  console.log('🤖 AI CLAUSE ANALYSIS REQUEST');
  console.log('='.repeat(60));
  
  const { clauses_text, language, clauses } = req.body;
  
  console.log('📝 Input length:', clauses_text?.length || 0, 'characters');
  console.log('🌐 Language:', language || 'zh');
  console.log('📊 Clauses count:', clauses?.length || 0);
  
  if (!clauses_text || clauses_text.trim().length === 0) {
    return res.status(400).json({
      success: false,
      error: 'No clauses text provided'
    });
  }
  
  try {
    const aiResult = await analyzeClausesWithAI(clauses_text, language || 'zh');
    
    if (aiResult) {
      const parsedClauses = parseBilingualResponse(aiResult);
      
      const resultClauses = parsedClauses.map((parsed, index) => {
        const existingClause = clauses?.[index] || {};
        return {
          clause_number: existingClause.clause_number || index + 1,
          clause_text: parsed.clause_text || existingClause.clause_text || '',
          chinese_explanation: parsed.chinese_explanation || '',
          risk_level: existingClause.risk_level || 'safe',
          analysis: existingClause.analysis || '',
          suggestion: existingClause.suggestion || ''
        };
      });
      
      console.log('✅ AI analysis completed, parsed', resultClauses.length, 'clauses');
      res.json({
        success: true,
        data: {
          clauses: resultClauses,
          raw_text: aiResult
        }
      });
    } else {
      console.log('⚠️ AI analysis returned empty');
      res.json({
        success: false,
        error: 'AI analysis failed'
      });
    }
  } catch (error) {
    console.error('❌ AI analysis error:', error.message);
    res.status(500).json({
      success: false,
      error: 'AI analysis failed',
      details: error.message
    });
  }
});

app.use((err, req, res, next) => {
  console.error('Error:', err);
  res.status(err.status || 500).json({
    success: false,
    error: err.message || 'Internal server error'
  });
});

app.use((req, res) => {
  res.status(404).json({
    success: false,
    error: 'Endpoint not found'
  });
});

db.initializeDatabase(dbPath);

app.listen(PORT, () => {
  console.log('\n🚀 QiYoga Backend is running!');
  console.log(`📍 Port: ${PORT}`);
  console.log(`🔗 Health check: http://localhost:${PORT}/health`);
  console.log(`🪝 Webhook endpoint: http://localhost:${PORT}/webhook/paddle`);
  console.log(`📄 OCR endpoint: http://localhost:${PORT}/api/lease/analyze`);
  console.log(`📊 Database: ${dbPath}`);
  console.log(`✅ Allowed origins: ${ALLOWED_ORIGINS.join(', ')}`);
  console.log(`🔐 PADDLE_WEBHOOK_SECRET configured: ${!!process.env.PADDLE_WEBHOOK_SECRET}\n`);
});
