const express = require('express');
const multer = require('multer');
const pdfParse = require('pdf-parse');
const router = express.Router();

const storage = multer.memoryStorage();
const upload = multer({
  storage: storage,
  limits: {
    fileSize: 5 * 1024 * 1024,
    files: 1
  },
  fileFilter: (req, file, cb) => {
    if (file.mimetype === 'application/pdf') {
      cb(null, true);
    } else {
      cb(new Error('Only PDF files are allowed'), false);
    }
  }
});

router.post('/api/ocr', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({
        success: false,
        error: 'No file uploaded'
      });
    }

    const dataBuffer = req.file.buffer;
    const data = await pdfParse(dataBuffer);

    console.log('✅ PDF parsed successfully');
    console.log('Pages:', data.numpages);
    console.log('Text length:', data.text.length);

    const leaseTerms = {
      rent: extractAmount(data.text),
      leaseTerm: extractLeaseTerm(data.text),
      securityDeposit: extractAmount(data.text),
      lateFees: extractAmount(data.text),
      pets: extractPetPolicy(data.text),
      subletting: extractSublettingPolicy(data.text)
    };

    res.json({
      success: true,
      text: data.text,
      info: {
        pages: data.numpages,
        info: data.info
      },
      leaseTerms: leaseTerms
    });
  } catch (error) {
    console.error('❌ Error parsing PDF:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

function extractAmount(text) {
  const match = text.match(/\$?\s*[\d,]+/);
  if (match) {
    return match[0].replace(/[\$,]/g, '');
  }
  return null;
}

function extractLeaseTerm(text) {
  const match = text.match(/term\s*[:\s]*(\d+)\s*(month|year|months)/i);
  if (match) {
    return `${match[0]} ${match[1]}${match[2]}`;
  }
  return null;
}

function extractPetPolicy(text) {
  if (/no\s*pets/i.test(text)) {
    return 'Not allowed';
  }
  if (/pets?\s*allowed/i.test(text)) {
    return 'Allowed with restrictions';
  }
  if (/pet\s*allowed/i.test(text)) {
    return 'Allowed';
  }
  return null;
}

function extractSublettingPolicy(text) {
  if (/no\s*subletting/i.test(text)) {
    return 'Not allowed';
  }
  if (/subletting?\s*allowed/i.test(text)) {
    return 'Allowed with restrictions';
  }
  if (/subletting?\s*allowed/i.test(text)) {
    return 'Allowed with landlord approval';
  }
  return null;
}

module.exports = router;
