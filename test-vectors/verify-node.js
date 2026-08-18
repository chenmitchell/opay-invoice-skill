#!/usr/bin/env node
/**
 * 歐付寶電子發票 AES 加解密測試向量驗證器（Node.js 版）。
 *
 * 用法：
 *     node test-vectors/verify-node.js [aes-encryption.json 路徑]
 *
 * 只用 Node 內建 crypto，無外部相依。輸出格式與 verify.py 完全一致 ——
 * 兩個獨立實作算出同樣結果，才能證明 references/encryption-aes.md 把規格描述正確了。
 *
 * 全部通過印出 "N/N pass" 並 exit 0；任一失敗 exit 1。
 */
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// .NET 慣例的 URLEncode / URLDecode（見 references/urlencode-table.md）
// 安全字元集：A-Z a-z 0-9 - _ . ! * ( )
// 半形空格 -> '+'；其餘位元組 -> %XX（大寫十六進位）
// ---------------------------------------------------------------------------
const SAFE = new Set(
  'ABCDEFGHIJKLMNOPQRSTUVWXYZ' +
  'abcdefghijklmnopqrstuvwxyz' +
  '0123456789-_.!*()'
);

function opayUrlencode(text) {
  const bytes = Buffer.from(text, 'utf8');
  let out = '';
  for (const byte of bytes) {
    const char = String.fromCharCode(byte);
    if (SAFE.has(char)) out += char;
    else if (char === ' ') out += '+';
    else out += '%' + byte.toString(16).toUpperCase().padStart(2, '0');
  }
  return out;
}

function opayUrldecode(text) {
  const bytes = [];
  for (let i = 0; i < text.length; ) {
    const char = text[i];
    if (char === '+') { bytes.push(0x20); i += 1; }
    else if (char === '%') { bytes.push(parseInt(text.substr(i + 1, 2), 16)); i += 3; }
    else { bytes.push(...Buffer.from(char, 'utf8')); i += 1; }
  }
  return Buffer.from(bytes).toString('utf8');
}

// ---------------------------------------------------------------------------
// AES-128-CBC + PKCS7（Node 內建 crypto 預設即為 PKCS7，setAutoPadding(true)）
// ---------------------------------------------------------------------------
function opayEncrypt(key, iv, plaintext) {
  const encoded = opayUrlencode(plaintext);
  const cipher = crypto.createCipheriv('aes-128-cbc', Buffer.from(key, 'utf8'), Buffer.from(iv, 'utf8'));
  cipher.setAutoPadding(true);
  return Buffer.concat([cipher.update(encoded, 'utf8'), cipher.final()]).toString('base64');
}

function opayDecrypt(key, iv, ciphertextB64) {
  const decipher = crypto.createDecipheriv('aes-128-cbc', Buffer.from(key, 'utf8'), Buffer.from(iv, 'utf8'));
  decipher.setAutoPadding(true);
  const raw = Buffer.concat([
    decipher.update(Buffer.from(ciphertextB64, 'base64')),
    decipher.final(),
  ]).toString('utf8');
  return opayUrldecode(raw);
}

// ---------------------------------------------------------------------------
// 驗證主流程
// ---------------------------------------------------------------------------
function main() {
  const here = __dirname;
  const file = process.argv[2] || path.join(here, 'aes-encryption.json');
  const doc = JSON.parse(fs.readFileSync(file, 'utf8'));

  const vectors = doc.vectors;
  const failures = [];

  console.log('opay-invoice-skill AES 測試向量驗證（Node.js / 內建 crypto）');
  console.log('向量檔：' + path.relative(here, file));
  console.log('');

  for (const vec of vectors) {
    const problems = [];

    const actualEncoded = opayUrlencode(vec.plaintext);
    if (actualEncoded !== vec.urlencoded) {
      problems.push('urlencode 不符\n      expected: ' + vec.urlencoded +
                    '\n      actual  : ' + actualEncoded);
    }

    const actualCipher = opayEncrypt(vec.key, vec.iv, vec.plaintext);
    if (actualCipher !== vec.ciphertext) {
      problems.push('encrypt 不符\n      expected: ' + vec.ciphertext +
                    '\n      actual  : ' + actualCipher);
    }

    let actualPlain = null;
    try {
      actualPlain = opayDecrypt(vec.key, vec.iv, vec.ciphertext);
    } catch (err) {
      problems.push('decrypt 例外：' + err.message);
    }
    if (actualPlain !== null && actualPlain !== vec.plaintext) {
      problems.push('decrypt 不符\n      expected: ' + vec.plaintext +
                    '\n      actual  : ' + actualPlain);
    }

    if (problems.length) {
      failures.push(vec.id);
      console.log('  FAIL  ' + vec.id);
      for (const p of problems) console.log('    - ' + p);
    } else {
      console.log('  ok    ' + vec.id + '  (' + vec.source + ')');
    }
  }

  console.log('');
  console.log((vectors.length - failures.length) + '/' + vectors.length + ' pass');
  if (failures.length) {
    console.log('failed: ' + failures.join(', '));
    return 1;
  }
  return 0;
}

process.exit(main());
