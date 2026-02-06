const pdfParse = require('pdf-parse');

async function parsePDF(buffer) {
  try {
    const data = await pdfParse(buffer);
    return {
      success: true,
      text: data.text,
      numpages: data.numpages,
      info: data.info
    };
  } catch (error) {
    console.error('PDF parsing error:', error);
    return {
      success: false,
      error: error.message
    };
  }
}

function extractLeaseTerms(text) {
  const terms = {
    rent: null,
    leaseTerm: null,
    securityDeposit: null,
    lateFees: null,
    pets: null,
    subletting: null
  };

  const rentMatch = text.match(/rent\s*:?\s*\$?([\d,]+)/i);
  if (rentMatch) terms.rent = rentMatch[1];

  const termMatch = text.match(/lease\s*term\s*:?\s*(\d+)\s*(month|year)/i);
  if (termMatch) {
    terms.leaseTerm = `${termMatch[1]} ${termMatch[2]}(s)`;
  }

  const depositMatch = text.match(/security\s*deposit\s*:?\s*\$?([\d,]+)/i);
  if (depositMatch) terms.securityDeposit = depositMatch[1];

  const lateFeeMatch = text.match(/late\s*fee\s*:?\s*\$?([\d,]+)/i);
  if (lateFeeMatch) terms.lateFees = lateFeeMatch[1];

  if (/no\s*pets/i.test(text)) {
    terms.pets = 'Not allowed';
  } else if (/pets\s*allowed/i.test(text)) {
    terms.pets = 'Allowed with restrictions';
  }

  if (/no\s*subletting/i.test(text)) {
    terms.subletting = 'Not allowed';
  } else if (/subletting\s*allowed/i.test(text)) {
    terms.subletting = 'Allowed with restrictions';
  }

  return terms;
}

module.exports = {
  parsePDF,
  extractLeaseTerms
};
