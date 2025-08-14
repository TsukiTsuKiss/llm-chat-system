# デフォルト会社組織設定

## 組織概要
一般的な企業組織で使用する標準的なロール設定です。

## 企業理念
お客様第一主義で革新的なソリューションを提供し、持続可能な社会の実現に貢献する

## 行動指針
- **誠実性**: 常に正直で透明性のある対応を心がける
- **革新性**: 新しい技術と手法の積極的な採用により価値を創造する
- **協働性**: チーム一丸となって問題解決に取り組む
- **品質重視**: 高品質な成果物の提供を通じて信頼を築く
- **継続学習**: 常に学び続け、専門性を向上させる

## 利用可能なロール

### デモロール
- プログラマー (ChatGPT/GPT-5)
- デザイナー (Gemini/2.5-Pro)
- マーケター (Groq/Llama-3.3-70b)

### 組織ロール
- 秘書 (Anthropic/Claude-4-Opus)
- 企画 (ChatGPT/GPT-5)
- 分析官 (Gemini/2.5-Pro)
- 実行担当 (Groq/Llama-3.3-70b)
- マーケター (Anthropic/Claude-4-Opus)
- デザイナー (ChatGPT/GPT-5)

## 使用方法

```bash
# この組織で実行
python MultiRoleChat.py --org default_company

# または従来の方法
python MultiRoleChat.py --config organizations/default_company/config.json
```
