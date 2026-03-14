# SQLクエリ集

このフォルダには、`model_costs.db`データベースで使用できるSQLクエリが含まれています。

## 使用方法

### 方法1: ファイルから実行

```bash
python model_costs_db.py sql-file sql/01_check_dates.sql
```

### 方法2: インタラクティブモードでコピペ

```bash
python model_costs_db.py sql-interactive
```

その後、SQLファイルの内容をコピーして貼り付け。

## クエリ一覧

| ファイル名 | 説明 |
|-----------|------|
| `01_check_dates.sql` | データベース内の日付とモデル数を確認 |
| `02_cheapest_models.sql` | 最も安いモデル TOP 20 |
| `03_provider_comparison.sql` | プロバイダー別の統計 |
| `04_price_changes.sql` | 価格変更があったモデル（2つの日付を比較） |
| `05_groq_models.sql` | Groqのモデル一覧 |
| `06_new_models.sql` | 新規追加されたモデル |
| `07_expensive_models.sql` | 最も高いモデル TOP 20 |
| `08_price_history.sql` | 特定モデルの価格履歴 |
| `09_search_models.sql` | モデル名やプロバイダーで検索 |

## 注意事項

- 一部のクエリでは、日付やモデル名を実際のデータに合わせて変更する必要があります
- コメント（`--`）を参考に、適宜クエリを調整してください

## カスタマイズ

これらのSQLファイルをコピーして、独自のクエリを作成することもできます。

## テーブル構造

```sql
CREATE TABLE model_costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_updated TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_cost_per_1k_tokens REAL NOT NULL,
    output_cost_per_1k_tokens REAL NOT NULL,
    currency TEXT DEFAULT 'USD',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, model, date_updated)
);
```

