from MultiRoleChat import MultiRoleManager, load_ai_assistants_config

def test_final_code_saving():
    """最終コード保存機能のテスト"""
    # AI設定を読み込み
    ai_assistants = load_ai_assistants_config()
    
    # MultiRoleManagerを初期化
    role_manager = MultiRoleManager(
        ai_assistants=ai_assistants,
        use_fast=True
    )
    
    # テスト用のレスポンスを手動で蓄積（実際のAI呼び出しなし）
    role_manager.workflow_responses = [
        {
            'role': 'プログラマー',
            'response': '''
Pythonの簡単な計算機プログラムを作成します：

```python
def calculator():
    while True:
        try:
            num1 = float(input("最初の数値を入力してください: "))
            operator = input("演算子を入力してください (+, -, *, /): ")
            num2 = float(input("2番目の数値を入力してください: "))
            
            if operator == '+':
                result = num1 + num2
            elif operator == '-':
                result = num1 - num2
            elif operator == '*':
                result = num1 * num2
            elif operator == '/':
                if num2 != 0:
                    result = num1 / num2
                else:
                    print("ゼロで割ることはできません")
                    continue
            else:
                print("無効な演算子です")
                continue
            
            print(f"結果: {result}")
            
            if input("続行しますか? (y/n): ").lower() != 'y':
                break
        except ValueError:
            print("無効な入力です")

if __name__ == "__main__":
    calculator()
```
            ''',
            'timestamp': '2025-08-19T00:00:00'
        },
        {
            'role': 'テスター',
            'response': '''
テスト用のHTMLインターフェースも作成します：

```html
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Web計算機</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 400px; margin: 50px auto; }
        .calculator { border: 1px solid #ccc; padding: 20px; border-radius: 8px; }
        input, button { margin: 5px; padding: 10px; }
        button { background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
        #result { margin-top: 20px; padding: 10px; background: #f8f9fa; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="calculator">
        <h2>Web計算機</h2>
        <input type="number" id="num1" placeholder="数値1">
        <select id="operator">
            <option value="+">+</option>
            <option value="-">-</option>
            <option value="*">×</option>
            <option value="/">/</option>
        </select>
        <input type="number" id="num2" placeholder="数値2">
        <button onclick="calculate()">計算</button>
        <div id="result"></div>
    </div>
    
    <script>
        function calculate() {
            const num1 = parseFloat(document.getElementById('num1').value);
            const operator = document.getElementById('operator').value;
            const num2 = parseFloat(document.getElementById('num2').value);
            const resultDiv = document.getElementById('result');
            
            if (isNaN(num1) || isNaN(num2)) {
                resultDiv.innerHTML = '<span style="color: red;">有効な数値を入力してください</span>';
                return;
            }
            
            let result;
            switch (operator) {
                case '+': result = num1 + num2; break;
                case '-': result = num1 - num2; break;
                case '*': result = num1 * num2; break;
                case '/': 
                    if (num2 === 0) {
                        resultDiv.innerHTML = '<span style="color: red;">ゼロで割ることはできません</span>';
                        return;
                    }
                    result = num1 / num2; 
                    break;
            }
            
            resultDiv.innerHTML = `<strong>結果: ${result}</strong>`;
        }
    </script>
</body>
</html>
```
            ''',
            'timestamp': '2025-08-19T00:01:00'
        }
    ]
    
    # 最終コード保存をテスト
    print("🔧 最終コード保存機能をテスト中...")
    role_manager._save_workflow_final_code("計算機プログラム作成", "test_calculator")
    
    print("✅ テスト完了")

if __name__ == "__main__":
    test_final_code_saving()
