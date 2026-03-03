# 入退室管理システム（バックエンド）📷

カメラ映像から顔を認識して部室の入退室を管理するシステムです。
<img width="1553" height="900" alt="image" src="https://github.com/user-attachments/assets/3ba55c67-f945-4396-82d5-c8f6883192c6" />

## 概要

Raspberry Piに接続したカメラで人物を検出・識別し、入退室の記録をリアルタイムでWebアプリに反映します。部室の利用状況を可視化することで、オープンで活気ある空間の雰囲気づくりを目的に開発しました。

このリポジトリは **バックエンド（Python / FastAPI）** を管理しています。フロントエンド側は[こちら](https://github.com/higuchi-learn/koukaten2025)。

## 技術スタック

| 領域 | 技術 |
|------|------|
| バックエンド | Python / FastAPI |
| データベース | MariaDB |
| 画像処理 | Raspberry Pi カメラ / face_recognition |
| 通信 | REST API |

## 私の担当

- FastAPIによるサーバー通信設計・実装
- MariaDBとの連携・DB設計
- 特徴量比較による入退室者判定処理の実装

## 学び・反省

システムとしては動作しましたが、`face_recognition` ライブラリの内部動作を十分に理解しないまま使用したため、認識精度に課題が生じました。**ライブラリをブラックボックスのまま使うことの危険性**を身をもって学び、使用するライブラリの仕組みを理解してから採用することの重要性を認識しました。

## リンク

- 発表資料: https://www.canva.com/design/DAG1Mb6DHuk/p7vP5TPRKIIREpATK6HkZQ/view
- フロントエンド側リポジトリ: https://github.com/higuchi-learn/koukaten2025
