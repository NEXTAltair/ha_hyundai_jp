# Unknowns Discovery Rules

プロンプト・ルール・計画に書かれていない前提を推測で埋めず、**unknowns** として明示し、
調査・質問・仮定・延期のどれで扱ったかを成果物に残すためのルール。

「自分で確認できることは聞かずに確認する」「ユーザーの意図・スコープ・価値判断に関わることだけ聞く」
「小さく可逆な判断は仮定して進め、仮定として明示する」という判断そのものは現行モデルの既定挙動であり、
ここでは繰り返さない。本ファイルが定めるのは **記録の形式** と **手を止める条件** だけ。

## 適用条件

- 新機能、バグ修正、設計変更、複数ファイル変更、PR 作成を伴う作業
- 要件が曖昧、または成功条件・検証方法・不変制約が不足している作業

typo 修正・フォーマットのみの変更、1 コマンドで完了する read-only 作業では省略してよい。

## 入口: 着手前の棚卸し

設計変更や複数ファイル実装では、計画・PR description・作業メモのいずれかに次を残す。小さな作業では
口頭の短い整理でよい。

```markdown
## Known Facts
- 確認済みの事実

## Unknowns
- 未確定だが作業結果に影響すること

## Assumptions
- 未確認のまま進める仮定と、その理由

## Resolution Plan
- inspect: ローカルコード / docs / ADR / logs で確認するもの
- test: テスト / smoke / reproduce で確認するもの
- ask: ユーザーに確認するもの
- defer: 今回のスコープ外として明示するもの
```

実 API や実モデルなど決定論的でない検証は CI 必須ゲートと分けて扱う ([testing.md](testing.md))。
過去の設計判断・教訓は [planning-memory.md](planning-memory.md) の場所を inspect する。

## 途中: 再計画の停止条件

実装中に次を見つけたら、手を止めて unknowns を更新し、必要なら計画を組み直す。
再計画では「続行」「質問」「別案へ切替」「スコープ縮小」「エスカレーション」のどれかを明示する。

- 当初の前提と矛盾するコード、テスト、ログ、ADR を見つけた
- 局所修正のつもりが設計変更・責務変更・データ移行に膨らんだ
- 既存パターンに合わない新しい抽象や依存を追加しそうになった
- テストは通るが、要求を満たした根拠が弱い
- 同じ責務境界で修正と指摘が繰り返される

## 出口: 成果報告に残すもの

完了報告、PR description、調査結果、レビュー返答に含める。小さな変更では `Verified` だけで十分。
複雑な変更や推測を含む変更では `Assumptions` と `Not Verified` を省略しない。
今回扱わない unknown は黙って落とさず `Not Verified` / `Follow-up` に残し、対応が必要なら
Issue・TODO・ADR 提案など導入先の記録先へつなぐ。

```markdown
## Verified
- 実行した検証、確認したログ、読んだ記録

## Assumptions
- 未確認のまま置いた仮定

## Not Verified
- 今回確認していないこと

## Follow-up
- 後続 Issue / ADR / 手動確認が必要なこと
```

## 関連

- [planning-memory.md](planning-memory.md): 過去判断・教訓を inspect する入口
- [testing.md](testing.md): test で unknown を解消する検証方針
- [git-workflow.md](git-workflow.md): 実装・PR・エスカレーションの運用境界
- `prompt-optimizer` / `goal-prompt-crafter` skill: 要件や完了条件が曖昧な場合の補助
