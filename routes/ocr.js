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

    res.json({
      success: true,
      text: data.text,
      info: {
        pages: data.numpages,
        info: data.info
      }
    });
  } catch (error) {
    console.error('❌ Error parsing PDF:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

module.exports = router;
