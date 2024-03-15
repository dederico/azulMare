from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
import base64
import binascii
import json
import requests

def encrypt_aes(s, key, IV):
    backend = default_backend()
    cipher = Cipher(algorithms.AES(key), modes.CBC(IV), backend=backend)
    encryptor = cipher.encryptor()

    # Pad the plaintext to a multiple of the block size
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(s.encode()) + padder.finalize()

    encrypted_bytes = encryptor.update(padded_data) + encryptor.finalize()
    encoded_bytes = base64.b64encode(encrypted_bytes)
    return encoded_bytes.hex()

def decrypt_aes(encrypted_bytes, key, IV):
    backend = default_backend()
    cipher = Cipher(algorithms.AES(key), modes.CBC(IV), backend=backend)
    decryptor = cipher.decryptor()
    decrypted_bytes = decryptor.update(base64.b64decode(encrypted_bytes)) + decryptor.finalize()
    return decrypted_bytes.decode().rstrip('\0')

# Convert hexadecimal strings to bytes
IV_hex = "477522fb7825b4b691f6a990edfacbc4"
Key_hex = "56b9ec57bdb4424aab5ca463c9647d06"

IV = binascii.unhexlify(IV_hex)
Key = binascii.unhexlify(Key_hex)

# Example plaintext input string to be encrypted
plaintext = "Hello, world!"

# Encrypt the plaintext using AES encryption
encrypted_text = encrypt_aes(plaintext, Key, IV)
print("Encrypted text:", encrypted_text)

# Make a POST request to the GetAES endpoint with your plaintext input string
url = "https://paycips.com/v20/TEST/Api/GetAES/100"
payload = {
    "inputString": encrypted_text
}
headers = {
    "Content-Type": "application/json"
}
response = requests.post(url, data=json.dumps(payload), headers=headers)

# Parse the response
if response.status_code == 200:
    data = response.json()
    if data["Status"]:
        # Extract the encrypted result from the response
        encrypted_result_from_endpoint = data["ResultString"]

        # Decrypt the result obtained from the endpoint
        decrypted_result_from_endpoint = decrypt_aes(encrypted_result_from_endpoint, Key, IV)

        # Compare the decrypted result with the original plaintext
        if decrypted_result_from_endpoint == plaintext:
            print("Encryption and decryption successful!")
        else:
            print("Encryption or decryption failed: Results do not match.")
    else:
        print("Error: Transaction was not successful.")
else:
    print("Error:", response.status_code)
