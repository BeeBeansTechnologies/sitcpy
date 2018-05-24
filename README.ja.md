## SiTCP Software development Support Library

PythonでのSiTCPデバイス用ソフトウェア開発サポートライブラリです。

* プログラム言語: Python 2.6, 2.7, 3.3+
* ライセンス: MIT License

Read this in other languages: [English](README.md), [日本語](README.ja.md)

![SiTCP](docs/images/sitcp.png)


### SiTCPとは

* 物理学実験での大容量データ転送を目的としてFPGA（Field Programmable Gate Array）上に実装されたシンプルなTCP/IPです。
* TCPセッションで高速で信頼性のあるデータ転送を行えます。
* RBCP(UDP)によるレジスタアクセスをサポートしており、機器側ファームウェアや計算機側ドライバなど面倒な部分を省いてシンプルにシステムを構成できます。
* このプロジェクトはSiTCPを提供するものではありません。

SiTCPについては[SiTCPライブラリページ](https://www.bbtech.co.jp/products/sitcp-library/)を参照してください。


### sitcpyとは

* SiTCPを使用して開発されたデバイス用ソフトウェア開発をサポートするPythonライブラリです。
* SiTCP RBCP(UDP)用 API（SiTCPデバイスのレジスタ読み書き用）。
* TCPデータ収集用汎用クラスライブラリ。
* SiTCP 疑似デバイス開発サポートクラスライブラリ。
    * RBCP用疑似メモリ、疑似サーバー。
    * TCP疑似データ作成サポート。
* SiTCPがどのようなものか？をソフトウェアの視点から理解いただけるものです。


### ターゲットSiTCPデバイス

SiTCPを利用したデバイスのデザイン例はいくつかありますが、本ライブラリでは、SiTCPを使用した典型的なデバイスを想定しています。

* RBCPによるレジスタの設定をサポートしている。
* TCPに接続すると固定長のイベントデータを送信してくる。
* 接続後、イベントデータの先頭からデータが読み出せる。

![DAQ system](docs/images/daq-system.png)

やや扱いが難しくなるデバイスは

* レジスタ設定もTCPにしている。
* イベントデータの受信時に要求・応答型プロトコルがある、可変長のデータを処理する。


### インストール

pipコマンドを使用してインストールしてください。

```
pip install sitcpy
```

ソースコードからインストールする場合は次のようにしてください。

```
python setup.py sdist
pip install dist/sitcpy-x.x.x.tar.gz
```


### チュートリアル

sitcpy コマンドを使用して、SiTCP デバイスから DAQ を行うプロジェクトを作成できます。
プロジェクトには、シンプルな SiTCP 擬似デバイスが含まれます。
これらのプログラムは、telnet 等から CUI を通して操作します。

sitcpy コマンドの詳細は、ヘルプを参照してください。

```
sitcpy --help
```

ターミナルから、作成したいプロジェクトの親ディレクトリへ移動します。続いて、以下のようにコマンドを実行します。

```
sitcpy createcuiproject myproject
```

現在のディレクトリに、myproject ディレクトリが作成され、Python プログラムが配置されます。

* daq.py ... SiTCP デバイスから DAQ を行うプログラム
* pseudo.py ... SiTCP 擬似デバイス

これらのプログラムを使用して、実際に DAQ を行ってみましょう。まず、SiTCP 擬似デバイスを起動します。

```
python pseudo.py
```

DAQ プログラムを起動します。

```
python daq.py -p 5555
```

telnet コマンドを使用して、DAQ プログラムへ接続します。

```
telnet localhost 5555
```

telnet から、help コマンドを実行すると、利用可能なコマンド一覧が表示されます。

```
daq$ help
```

DAQ を開始するにあたって、Raw データファイルの保存を有効にします。

```
daq$ rawsave on
```

DAQ を開始します。

```
daq$ run
```

stat コマンドを使用すると、現在の DAQ 状態が表示されます。

```
daq$ stat
```

DAQ を終了します。

```
daq$ stop
```

myproject/log ディレクトリに、Raw データファイルが保存されました。

Raw データファイルの保存先や、接続先 SiTCP デバイスの設定は、config.json で変更できます。


### ライブラリ概略

#### command.py

sitcpy コマンドの実装です。

#### cui.py

コマンド処理をするサーバーを作成するためのライブラリ（汎用）です。
CommandHandlerの派生クラスを入れ替えることでカスタマイズします。
CommandClient クラスを使用して、telnet 等を使用せず、Python プログラムから CUI コマンドを実行できます。

#### daq_client.py

基本的な DAQ 機能を提供するためのライブラリです。

#### rbcp_server.py

SiTCP 擬似デバイスを作成するためのライブラリです。

#### rbcp.py

SiTCP デバイスへ RBCP パケットを送信するためのライブラリです。
