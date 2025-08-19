#!/usr/bin/env python3
"""
MultiRoleChat.py用のコード保存機能
AIが生成したコードをsandboxフォルダに保存し、実行結果を管理
"""

import os
import re
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

class CodeSaver:
    """コード保存とサンドボックス連携管理"""
    
    def __init__(self, sandbox_dir: str = "sandbox"):
        self.sandbox_dir = Path(sandbox_dir)
        self.sandbox_dir.mkdir(exist_ok=True)
        
        # 実行結果保存ディレクトリ
        self.results_dir = self.sandbox_dir / "results"
        self.results_dir.mkdir(exist_ok=True)
        
        # セッション管理
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = self.sandbox_dir / f"session_{self.session_id}"
        self.session_dir.mkdir(exist_ok=True)
    
    def extract_code_blocks(self, text: str) -> List[Dict]:
        """AIレスポンスからコードブロックを抽出"""
        pattern = r'```(\w+)?\n(.*?)\n```'
        matches = re.findall(pattern, text, re.DOTALL)
        
        code_blocks = []
        for i, (language, code) in enumerate(matches):
            if not language:
                language = "text"
            
            # 実行可能な言語のみ処理（WebファイルもOK）
            if language.lower() in ['python', 'py', 'javascript', 'js', 'node', 'bash', 'sh', 'html', 'css', 'json']:
                code_blocks.append({
                    "id": f"{self.session_id}_{i:03d}",
                    "language": language.lower(),
                    "code": code.strip(),
                    "filename": self._generate_filename(language.lower(), i)
                })
        
        return code_blocks
    
    def _generate_filename(self, language: str, index: int) -> str:
        """言語に応じたファイル名生成"""
        extensions = {
            'python': 'py',
            'py': 'py',
            'javascript': 'js',
            'js': 'js',
            'node': 'js',
            'bash': 'sh',
            'sh': 'sh',
            'html': 'html',
            'css': 'css',
            'json': 'json'
        }
        
        # 特定ファイル名のマッピング
        special_files = {
            'html': 'index.html',
            'css': 'styles.css',
            'json': 'package.json',
            'javascript': 'script.js',
            'js': 'script.js'
        }
        
        if language in special_files:
            return special_files[language]
        
        ext = extensions.get(language, 'txt')
        return f"code_{index:03d}.{ext}"
    
    def save_code_blocks(self, ai_response: str, metadata: Optional[Dict] = None) -> List[Dict]:
        """コードブロックをファイルに保存"""
        code_blocks = self.extract_code_blocks(ai_response)
        
        # Webアプリの場合、HTMLやCSSをレスポンステキストから抽出
        web_files = self._extract_web_files(ai_response)
        code_blocks.extend(web_files)
        
        saved_files = []
        
        for block in code_blocks:
            # コードの前処理（```マーカー除去など）
            cleaned_code = self._clean_code(block['code'], block['language'])
            
            # ファイル保存
            file_path = self.session_dir / block['filename']
            file_path.write_text(cleaned_code, encoding='utf-8')
            
            # メタデータ作成
            metadata_info = {
                "id": block['id'],
                "language": block['language'],
                "filename": block['filename'],
                "file_path": str(file_path),
                "created_at": datetime.now().isoformat(),
                "session_id": self.session_id,
                "status": "saved",
                "metadata": metadata or {}
            }
            
            # メタデータ保存
            meta_file = self.session_dir / f"{block['filename']}.meta.json"
            meta_file.write_text(json.dumps(metadata_info, indent=2, ensure_ascii=False), encoding='utf-8')
            
            saved_files.append(metadata_info)
            print(f"💾 保存完了: {file_path}")
        
        return saved_files
    
    def _clean_code(self, code: str, language: str) -> str:
        """コードの前処理を行う"""
        # 先頭と末尾のコードブロックマーカーを除去
        lines = code.split('\n')
        
        # 先頭のマーカー除去
        if lines and lines[0].strip().startswith('```'):
            lines = lines[1:]
        
        # 末尾のマーカー除去
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        
        # HTMLの場合、<!DOCTYPE html>を追加（存在しない場合）
        if language == 'html':
            content = '\n'.join(lines).strip()
            if not content.lower().startswith('<!doctype'):
                if content.lower().startswith('<html'):
                    content = '<!DOCTYPE html>\n' + content
        else:
            content = '\n'.join(lines)
        
        return content
    
    def _extract_web_files(self, text: str) -> List[Dict]:
        """AIレスポンスからHTMLやCSSファイル内容を抽出"""
        web_files = []
        
        # HTML抽出（コードブロック外のものも含む）
        html_patterns = [
            r'```html\n(.*?)\n```',
            r'<!DOCTYPE html.*?</html>',
            r'<html.*?</html>'
        ]
        
        for i, pattern in enumerate(html_patterns):
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            for j, html_content in enumerate(matches):
                if html_content.strip():
                    web_files.append({
                        "id": f"web_html_{i}_{j}",
                        "language": "html",
                        "code": html_content.strip(),
                        "filename": "index.html"
                    })
                    break  # 最初のHTMLのみ
        
        # CSS抽出
        css_patterns = [
            r'```css\n(.*?)\n```',
        ]
        
        for i, pattern in enumerate(css_patterns):
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            for j, css_content in enumerate(matches):
                if css_content.strip():
                    web_files.append({
                        "id": f"web_css_{i}_{j}",
                        "language": "css",
                        "code": css_content.strip(),
                        "filename": "styles.css"
                    })
                    break  # 最初のCSSのみ
        
        return web_files
    
    def create_execution_script(self, saved_files: List[Dict]) -> str:
        """Docker実行用のスクリプト作成"""
        script_lines = ["#!/bin/bash", ""]
        script_lines.append("# Auto-generated execution script")
        script_lines.append(f"# Session: {self.session_id}")
        script_lines.append(f"# Created: {datetime.now().isoformat()}")
        script_lines.append("")
        
        has_web_app = self._detect_web_app(saved_files)
        
        if has_web_app:
            # Webアプリケーションの場合の実行スクリプト
            script_lines.extend(self._create_webapp_script())
        else:
            # 通常のコード実行
            for file_info in saved_files:
                language = file_info['language']
                filename = file_info['filename']
                
                script_lines.append(f"echo '=== Executing {filename} ({language}) ==='")
                
                if language in ['python', 'py']:
                    script_lines.append(f"python {filename}")
                elif language in ['javascript', 'js', 'node']:
                    script_lines.append(f"node {filename}")
                elif language in ['bash', 'sh']:
                    script_lines.append(f"bash {filename}")
                
                script_lines.append("echo")
        
        # スクリプト保存
        script_path = self.session_dir / "run_all.sh"
        script_path.write_text('\n'.join(script_lines), encoding='utf-8')
        script_path.chmod(0o755)  # 実行権限付与
        
        return str(script_path)
    
    def _detect_web_app(self, saved_files: List[Dict]) -> bool:
        """Webアプリケーションかどうかを検出"""
        # HTMLファイルやCSSファイルが含まれているかチェック
        for file_info in saved_files:
            filename = file_info.get('filename', '')
            if filename.endswith('.html') or filename.endswith('.css'):
                return True
        return False
    
    def _create_webapp_script(self) -> List[str]:
        """Webアプリケーション用の実行スクリプト作成"""
        return [
            "# Webアプリケーション自動セットアップ",
            "echo '🌐 Webアプリケーションを自動セットアップしています...'",
            "",
            "# HTMLファイルを検索して自動構築",
            "if [ ! -f index.html ]; then",
            "    # HTMLコンテンツをファイルに展開",
            "    echo '📄 HTMLファイルを生成中...'",
            "    # JavaScriptからHTMLを抽出してファイル作成する処理をここに追加",
            "fi",
            "",
            "# Webサーバー起動",
            "echo '🚀 Webサーバーを起動しています...'",
            "echo 'アクセス先: http://localhost:8080'",
            "python3 -m http.server 8080 &",
            "SERVER_PID=$!",
            "echo \"サーバーPID: $SERVER_PID\"",
            "",
            "# 少し待ってからブラウザテスト",
            "sleep 3",
            "echo '🔍 動作確認中...'",
            "if command -v curl >/dev/null 2>&1; then",
            "    curl -s http://localhost:8080/ | head -20",
            "else",
            "    echo 'curl not found, manual check required'",
            "fi",
            "",
            "echo '✅ Webアプリが起動しました！'",
            "echo 'ブラウザで http://localhost:8080 にアクセスしてください'",
            ""
        ]
        script_path = self.session_dir / "run_all.sh"
        script_path.write_text('\n'.join(script_lines), encoding='utf-8')
        script_path.chmod(0o755)  # 実行権限付与
        
        return str(script_path)
    
    def save_ai_response_complete(self, ai_response: str, role_name: str, action: str) -> Dict:
        """AIレスポンス全体の保存（MultiRoleChat.py統合用）"""
        # コードブロック保存
        saved_files = self.save_code_blocks(ai_response)
        
        # メタデータ作成
        metadata = {
            "role_name": role_name,
            "action": action,
            "response_text": ai_response,
            "session_id": self.session_id
        }
        
        # 実行スクリプト作成（実行可能ファイルがある場合）
        script_path = None
        if saved_files:
            script_path = self.create_execution_script(saved_files)
        
        # セッション情報保存
        session_info = {
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(),
            "role_name": role_name,
            "action": action,
            "saved_files": saved_files,
            "execution_script": script_path,
            "sandbox_dir": str(self.session_dir)
        }
        
        session_file = self.session_dir / "session_info.json"
        session_file.write_text(json.dumps(session_info, indent=2, ensure_ascii=False), encoding='utf-8')
        
        return session_info

if __name__ == "__main__":
    # 単体テスト実行
    print("CodeSaver 単体テスト開始...")
    saver = CodeSaver()
    
    # シンプルなテスト用AI応答
    test_response = """
テスト用のコードです：

```python
print("Hello, World!")
```

```javascript
console.log("Hello, World!");
```
"""
    
    session_info = saver.save_ai_response_complete(test_response, "テストロール", "単体テスト")
    print(f"\n✅ テスト完了: {session_info['session_id']}")
    print(f"📁 保存先: {session_info['sandbox_dir']}")
    
    if session_info['saved_files']:
        print(f"💾 {len(session_info['saved_files'])} ファイル保存完了")
        if session_info['execution_script']:
            print(f"🚀 実行スクリプト: {session_info['execution_script']}")
