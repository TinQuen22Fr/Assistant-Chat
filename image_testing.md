Image rules (enforced before sending):
- Accepted MIME types: image/jpeg, image/png, image/webp only
- Animated images: frame 1 only (backend uses Pillow seek(0))
- Images resized to max 2048px side before encoding
- Don't send blank or solid-colour images
Test fixtures: /app/tests/fixtures/test.png (red square, blue circle, text "BANANE 42"), test.pdf (secret code ZEBRE-7731), test.docx (mascotte "Capitaine Hibou"), big.png (21 MB → must be rejected)
