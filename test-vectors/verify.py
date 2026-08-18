#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""歐付寶電子發票 AES 加解密測試向量驗證器（Python 版）。

用法：
    pip install pycryptodome
    python3 test-vectors/verify.py [aes-encryption.json 路徑]

行為與輸出格式與 verify-node.js 完全一致 —— 兩個獨立實作算出同樣結果，
才能證明 references/encryption-aes.md 把規格描述正確了。

全部通過印出 "N/N pass" 並 exit 0；任一失敗 exit 1。
"""
import base64
import json
import os
import sys

try:
    from Crypto.Cipher import AES
except ImportError:  # pragma: no cover
    sys.stderr.write("需要 pycryptodome：pip install pycryptodome\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# .NET 慣例的 URLEncode / URLDecode（見 references/urlencode-table.md）
# 安全字元集：A-Z a-z 0-9 - _ . ! * ( )
# 半形空格 -> '+'；其餘位元組 -> %XX（大寫十六進位）
# ---------------------------------------------------------------------------
_SAFE = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789-_.!*()"
)


def opay_urlencode(text):
    out = []
    for byte in text.encode("utf-8"):
        char = chr(byte)
        if char in _SAFE:
            out.append(char)
        elif char == " ":
            out.append("+")
        else:
            out.append("%%%02X" % byte)
    return "".join(out)


def opay_urldecode(text):
    buf = bytearray()
    i = 0
    while i < len(text):
        char = text[i]
        if char == "+":
            buf.append(0x20)
            i += 1
        elif char == "%" and i + 2 < len(text) + 1:
            buf.append(int(text[i + 1:i + 3], 16))
            i += 3
        else:
            buf.extend(char.encode("utf-8"))
            i += 1
    return buf.decode("utf-8")


# ---------------------------------------------------------------------------
# PKCS7 + AES-128-CBC
# ---------------------------------------------------------------------------
def _pkcs7_pad(data, block=16):
    n = block - (len(data) % block)
    return data + bytes([n]) * n


def _pkcs7_unpad(data, block=16):
    if not data or len(data) % block:
        raise ValueError("密文長度不是 %d 的倍數" % block)
    n = data[-1]
    if n < 1 or n > block or data[-n:] != bytes([n]) * n:
        raise ValueError("PKCS7 padding 不合法（金鑰/IV 錯誤，或對方用的不是 PKCS7）")
    return data[:-n]


def opay_encrypt(key, iv, plaintext):
    """明文 JSON -> URLEncode -> AES-128-CBC/PKCS7 -> Base64"""
    encoded = opay_urlencode(plaintext)
    cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
    return base64.b64encode(cipher.encrypt(_pkcs7_pad(encoded.encode("utf-8")))).decode("ascii")


def opay_decrypt(key, iv, ciphertext_b64):
    """Base64 -> AES-128-CBC/PKCS7 -> URLDecode -> 明文 JSON"""
    cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
    raw = _pkcs7_unpad(cipher.decrypt(base64.b64decode(ciphertext_b64)))
    return opay_urldecode(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# 驗證主流程
# ---------------------------------------------------------------------------
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "aes-encryption.json")

    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)

    vectors = doc["vectors"]
    failures = []

    print("opay-invoice-skill AES 測試向量驗證（Python / pycryptodome）")
    print("向量檔：%s" % os.path.relpath(path, here))
    print("")

    for vec in vectors:
        vid = vec["id"]
        problems = []

        actual_encoded = opay_urlencode(vec["plaintext"])
        if actual_encoded != vec["urlencoded"]:
            problems.append("urlencode 不符\n      expected: %s\n      actual  : %s"
                            % (vec["urlencoded"], actual_encoded))

        actual_cipher = opay_encrypt(vec["key"], vec["iv"], vec["plaintext"])
        if actual_cipher != vec["ciphertext"]:
            problems.append("encrypt 不符\n      expected: %s\n      actual  : %s"
                            % (vec["ciphertext"], actual_cipher))

        try:
            actual_plain = opay_decrypt(vec["key"], vec["iv"], vec["ciphertext"])
        except Exception as exc:  # noqa: BLE001
            actual_plain = None
            problems.append("decrypt 例外：%s" % exc)
        if actual_plain is not None and actual_plain != vec["plaintext"]:
            problems.append("decrypt 不符\n      expected: %s\n      actual  : %s"
                            % (vec["plaintext"], actual_plain))

        if problems:
            failures.append(vid)
            print("  FAIL  %s" % vid)
            for p in problems:
                print("    - %s" % p)
        else:
            print("  ok    %s  (%s)" % (vid, vec["source"]))

    print("")
    print("%d/%d pass" % (len(vectors) - len(failures), len(vectors)))
    if failures:
        print("failed: %s" % ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
