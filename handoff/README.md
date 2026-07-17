# handoff/ — 開発チーム通信欄

Composer（実装）・Copilot（レビュー）・オーナー（判断）のやり取りを残す場所です。

## ファイル

| ファイル | 役割 |
|---|---|
| `current.md` | **常に最新1枚だけ**。Phase やコミットごとに上書きする |
| `templates/review_request.md` | Composer → Copilot 依頼の雛形 |
| `templates/review_response.md` | Copilot 返答の雛形 |

変遷は Git の履歴で追います（`minutes/` と同じ考え方）。

```bash
git log --follow handoff/current.md
```

## 運用フロー

1. **Composer** … 実装後、`current.md` のメタと「Composer → Copilot」を書く
2. **Copilot** … レビューし「Copilot → Composer」に追記
3. **オーナー** … 「オーナー判断」に採用/却下を書く
4. 次 Phase 前に `current.md` を上書き（またはテンプレから再作成）

## Copilot への依頼

### 自動で読むか？

| 経路 | 読む？ | 備考 |
|---|---|---|
| `.github/copilot-instructions.md` | **部分的に** | ワークスペース指示として Copilot Chat に載る設定なら、`handoff/current.md` を見るよう書いてある |
| `#file handoff/current.md` | **確実** | チャットに明示添付。これが最も確実 |
| `@workspace` のみ | **不確実** | 関連ファイルとして拾われることもあるが、毎回は保証されない |

**結論:** 自動参照は補助。最小限の指示は **`#file` で添付 + 1行** が確実です。

### 最小指示（コピペ用）

```
#file handoff/current.md
依頼欄どおりレビューし、返答欄に追記してください。
```

copilot-instructions が効いている環境では、次の1行でも動くことが多いです。

```
通信欄（handoff/current.md）どおりレビューして。
```

### 精度を上げるとき

```
#file handoff/current.md
#file docs/MultiRoleStudio/design.md
依頼欄の観点でレビューし、返答欄に判定と指摘を追記してください。
```

## 設計との関係

- **Phase 進捗一覧** … `docs/MultiRoleStudio/design.md` **§9.0**（全体の ✅/⬜ はここが正本）
- **設計の正本** … `docs/MultiRoleStudio/design.md`（通信欄に設計変更を書かない）
- **通信欄** … 依頼・レビュー・オーナー判断の**手渡し**のみ
- 詳細 … design.md §1.6「記録ルール」
