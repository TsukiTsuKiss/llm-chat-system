## Copilot → Composer（返答テンプレ）

以下を `current.md` の「Copilot → Composer」欄に追記する。

```markdown
| 総合判定 | 条件付き合格 |
|---|---|

### 指摘

| 重要度 | ファイル | 内容 | design.md 参照 |
|---|---|---|---|
| major | `studio/engine.py` | （例）parallel 時のエラーメッセージが E205 と不一致 | §4.x |
| minor | `README.md` | （例）`--workflow` の説明が design と微妙にズレ | §9.1 |

### 良い点

- bindings と loader の責務分離が design に沿っている
- parity 試験で discussion / quiz の主要経路をカバーしている
```

### 重要度

| 級 | 意味 |
|---|---|
| blocker | マージ/Phase ゲート前に必修正 |
| major | 修正推奨（design ギャップ・バグの可能性） |
| minor | 任意（表現・リファクタ・ドキュメント） |

### 判定

| 判定 | 意味 |
|---|---|
| 合格 | 指摘なし、または minor のみ |
| 条件付き合格 | major ありだがオーナー判断で Phase 進行可 |
| 要修正 | blocker あり、または major が複数で設計逸脱が大きい |
