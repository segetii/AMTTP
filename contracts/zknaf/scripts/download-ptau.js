/**
 * Download Powers of Tau file for zkNAF trusted setup
 * Uses Hermez ceremony (widely trusted, 1000+ contributors)
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

const PTAU_FILES = {
  // Power of 2^14 = 16k constraints (enough for our circuits)
  14: 'https://hermez.s3-eu-west-1.amazonaws.com/powersOfTau28_hez_final_14.ptau',
  // Power of 2^16 = 65k constraints (for larger circuits)
  16: 'https://hermez.s3-eu-west-1.amazonaws.com/powersOfTau28_hez_final_16.ptau',
  // Power of 2^20 = 1M constraints (for very large circuits)
  20: 'https://hermez.s3-eu-west-1.amazonaws.com/powersOfTau28_hez_final_20.ptau',
};

const SELECTED_POWER = 16; // 65k constraints should be enough
const OUTPUT_DIR = path.join(__dirname, '..', 'trusted-setup');
const OUTPUT_FILE = path.join(OUTPUT_DIR, `pot${SELECTED_POWER}_final.ptau`);

async function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    console.log(`\n📥 Downloading Powers of Tau (2^${SELECTED_POWER})...`);
    console.log(`   Source: ${url}`);
    console.log(`   Destination: ${dest}\n`);

    const file = fs.createWriteStream(dest);
    let downloadedBytes = 0;
    let totalBytes = 0;

    https.get(url, (response) => {
      if (response.statusCode === 302 || response.statusCode === 301) {
        // Handle redirect
        https.get(response.headers.location, (redirectResponse) => {
          handleResponse(redirectResponse);
        });
      } else {
        handleResponse(response);
      }

      function handleResponse(res) {
        totalBytes = parseInt(res.headers['content-length'], 10);
        
        res.on('data', (chunk) => {
          downloadedBytes += chunk.length;
          const percent = ((downloadedBytes / totalBytes) * 100).toFixed(1);
          const mb = (downloadedBytes / 1024 / 1024).toFixed(1);
          const totalMb = (totalBytes / 1024 / 1024).toFixed(1);
          process.stdout.write(`\r   Progress: ${mb}MB / ${totalMb}MB (${percent}%)`);
        });

        res.pipe(file);

        file.on('finish', () => {
          file.close();
          console.log('\n\n✅ Download complete!\n');
          resolve();
        });
      }
    }).on('error', (err) => {
      fs.unlink(dest, () => {});
      reject(err);
    });
  });
}

async function main() {
  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║         AMTTP zkNAF - Powers of Tau Download               ║');
  console.log('╚════════════════════════════════════════════════════════════╝');

  // Create output directory
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    console.log(`\n📁 Created directory: ${OUTPUT_DIR}`);
  }

  // Check if file already exists
  if (fs.existsSync(OUTPUT_FILE)) {
    const stats = fs.statSync(OUTPUT_FILE);
    console.log(`\n⚠️  File already exists: ${OUTPUT_FILE}`);
    console.log(`   Size: ${(stats.size / 1024 / 1024).toFixed(1)}MB`);
    console.log('   Delete it manually if you want to re-download.\n');
    return;
  }

  try {
    await downloadFile(PTAU_FILES[SELECTED_POWER], OUTPUT_FILE);
    
    console.log('📋 Next steps:');
    console.log('   1. Run: npm run compile:all');
    console.log('   2. Run: npm run setup:all');
    console.log('   3. Run: npm run test\n');
  } catch (error) {
    console.error('\n❌ Download failed:', error.message);
    process.exit(1);
  }
}

main();
