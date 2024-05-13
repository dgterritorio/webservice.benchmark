# webservice.benchmark

- [English](README.md)
- [Português Europeu](README_PT.md)

Ferramentas de benchmark para serviços web OGC, scripts baseados na plataforma [locust - A modern load testing framework](https://locust.io/)  

Introdução ao locust: [quickstart](https://docs.locust.io/en/stable/quickstart.html)
Configuração geral e argumentos de comando: [Configuration and commands](https://docs.locust.io/en/stable/configuration.html)

O script de benchmark, por exemplo, `wmts.py`, adapta o Locust para testar especificamente os serviços OGC (por exemplo, `GetTiles`). Ele analisa o documento `GetCapabilities` e permite a personalização dos parâmetros de solicitação, como `TileMatrixSet` e `TileMatrix`.

Durante os testes, o Locust solicitará aleatoriamente um tile (`GetTile`). O script suporta parâmetros de semente aleatória para garantir a reprodutibilidade, gerando uma sequência consistente de números aleatórios.

## pyenv virtualenv

Instruções para instalação do pyenv: [Install Multiple Python Versions for Specific Project](https://gist.github.com/trongnghia203/9cc8157acb1a9faad2de95c3175aa875)  

pyenv virtual env install:

```bash
# pyenv python version install
export PYENV_PYTHON_VERSION="3.12.3"
PYTHON_CONFIGURE_OPTS=" --enable-optimizations --with-lto"  \
CPPFLAGS="-march=native -O3" \ 
CFLAGS="-march=native -O3" \ 
CXXFLAGS=${CFLAGS} pyenv install -v $PYENV_PYTHON_VERSION

pyenv virtualenv 3.12.3 webservice.benchmark
pyenv local webservice.benchmark 
pyenv shell webservice.benchmark
pyenv which pip # check if paths/shims are correct
#/home/mende012/.pyenv/versions/webservice.benchmark/bin/pip
```

## Instalar pacotes pythonn

O ficheiro `requirements.txt` especifica os pacotes e versões necessários para executar os scripts.

```bash
pip install -r requirements.txt
```

## Docker build and run

O arquivo requirements.txt especifica os pacotes e versões necessários para executar o script.

```bash
docker build --no-cache --progress=plain -t website.benchmark:v0.0.1 -f Dockerfile .
```

Para exemplo de execução do Docker, consulte a subseção sobre comandos WMS/WMTS.

## Comandos WMS (headless)

O script `wms.py` contém o código para testar um serviço WMS. Ele cria um framework de teste web com locust, estende e valida os argumentos da linha de comando.

```bash
# all possible configurations
locust -f wms.py --help
```

In a nutshell:

|Argumento|Descrição| Exemplo| Default |
|:------:|:---------:|:-------:|:---------:|
| `-h/-host`   | Host/Servidor com o caminho completo do serviço OGC | [https://ortos.dgterritorio.gov.pt/wms/ortoimagens2023](https://ortos.dgterritorio.gov.pt/wms/ortoimagens2023) | Obrigatório, sem valor default |
|`--headless`| Obrigatório, para poder correr na linha de comandos | --headless | Default e' o uso do  webgui|
|`--random-seed`|  Semente aleatória para gerar solicitações aleatórias |   --random-seed 2129 | 1640 |
|`--layer-name` | Camada de serviço OGC a ser usada | --layer-name Ortoimagens2023-IRG| Primeira camada encontrada no documento XML GetCapabilites |
|`--bbox-area`| Primeira camada encontrada no documento XML GetCapabilites| --bbox-area 50.0 | Default de 100.0|
|`--bbox-ratio` |Proporção largura/altura da bounding box| --bbox-ratio | Default of 1.0 (square)|  

Exemplo de comando:

```bash
locust -f wms.py  --host https://ortos.dgterritorio.gov.pt/wms/ortoimagens2023  --random-seed 7776 --bbox-area 100 --layer-name Ortoimagens2023-RGB   --headless -u 10 -r 1 -t 2m --html reports/ortoimagens2023_u10_r1_t2_s7776.html  --loglevel DEBUG --logfile logs/ortoimagens2023_u10_r1_t2_s7776.log 2>&1 |  tee reports/ortoimagens2023_u10_r1_t2_s7776.txt
```

Os gráficos finais e solicitações feitas estarão no ficheiro: `ortoimagens2023_u10_r1_t2_s7776.html` no directorio `reports`
Os ficheiros html podem ser abertos em qualquer navegador/browser normal.

### Execução em docker para serviço WMS

A execução do Docker esta preparada para usar `ENTRYPOINT ["locust"]`, portanto, todos os argumentos após locust podem/devem ser aceites:

```bash
mkdir reports logs
docker run --rm -v $(pwd)/reports:/reports -v $(pwd)/logs:/logs \
benchmark:v0.0.1 \  
-f wms.py --host https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0  \
--random-seed 4832 --bbox-area 100 --layer-name 2021_orthoHR  \
--headless -u 10 -r 1 -t 2m \ 
--html /reports/luchtfotorgb_u10_r1_t2_s4832.html \
--loglevel DEBUG --logfile /logs/luchtfotorgb_u10_r1_t2_s4832.log 
```

O commando implementa os directorios entre computador local e anfitrião (-v $(pwd)/reports:/reports -v $(pwd)/logs:/logs)o nome da imagem de docker `benchmark:v0.0.1`.

## Comandos WMTS (headless)

O script `wmts.py` contém o código para testar um serviço WMTS. Ele cria um framework de teste web com locust, estende e valida a entrada do usuário especificamente para WMTS.

```bash
# all possible configurations possible
locust -f wmts.py --help
```

Em resumo:

|Argumento|Descrição| Exemplo| Default |
|:------:|:---------:|:-------:|:---------:|
| `-h/-host`   | Host/Servidor com o caminho completo do serviço OGC | [https://cartografia.dgterritorio.gov.pt/ortos2021/service](https://cartografia.dgterritorio.gov.pt/ortos2021/service) | Obrigatório, sem padrão |
|`--headless`| Para o locust correm na linha de comando | --headless | Default e' o uso do  webgui|
|`--random-seed`|  Random seed to generate random request |   --random-seed 2129 | 1640 |
|`--layer-name`| Semente aleatória para gerar solicitações aleatórias | --layer-name Ortos2021-RGB | Primeira camada encontrada no documento XML `GetCapabilites`|
|`--tile-matrix-set`| TileMatrixSet da camada a ser testado (Tipo de Pirâmide )| --tile-matrix-set "PTTM_06"| Primeiro TileMatrixSet da camada encontrado no documento XML GetCapabilities|  
|`--tile-matrix`| TileMatrix do TileMatrixSet a ser usado (nível de zoom/resolução da pirâmide)| --tile-matrix "07"| Valor mediano (normalmente 07 ou 10)|
|`--u` | Número de solicitações (Número de usuários locust) | -u 10| Sem default |
|`-r` | Taxa de aumento de solicitações (Número de usuários locust) (Number of locust users)| -r 1| Sem default|
|`-t`| Tempo de teste, tempo total para executar o teste (s, m, h)| -t 4m | Sem default|
|`--loglevel`| Nível de log do Python, por exemplo, DEBUG, INFO| --loglevel DEBUG | INFO |
|`--html`| Nome do ficheiro HTML com resultados e gráficos do teste| --html wmts.ortos2021.r1.u1.s1640.report.html| No default |
|`--logfile`| Ficheiro de log com informações e solicitações adicionai| --logfile wmts.ortos2021.r1.u1.s1640.log| No default|

Exemplo de comando:

```bash
locust -f wmts.py --headless --host https://cartografia.dgterritorio.gov.pt/ortos2021/service  --random-seed 2129  -u 10 -r 1 -t 2m --layer-name Ortos2021-RGB    --html wms.ortos2021.r1.u1.s1640.report.html --loglevel DEBUG --logfile wmts.ortos2021.r1.u1.s1640.log 2>&1 | tee wmts.ortos2021.r1.u1.s1640.txt
```

Note: `2>&1 | tee wmts.ortos2021.r1.u1.s1640.txt` canalizará o conteúdo do console bash para o ficheiro `wmts.ortos2021.r1.u1.s1640.txt`

### Execução em docker para serviço WMTS

A execução do Docker esta preparada para usar `ENTRYPOINT ["locust"]`, portanto, todos os argumentos após locust podem/devem ser aceites:

```bash
mkdir reports logs
docker run --rm -v $(pwd)/reports:/reports -v $(pwd)/logs:/logs \
benchmark:v0.0.1 \  
-f wmts.py --host  https://cartografia.dgterritorio.gov.pt/ortos2021/service   \
--random-seed 2129 --bbox-area 100 --layer-name Ortos2021-RGB  \
--headless -u 10 -r 1 -t 2m \ 
--html /reports/wmts.ortos2021_u10_r1_t2_s4832.html \
--loglevel DEBUG --logfile /logs/wmts.ortos2021_u10_r1_t2_s4832.log 
```

O commando implementa os directorios entre computador local e anfitrião (-v $(pwd)/reports:/reports -v $(pwd)/logs:/logs)o nome da imagem de docker `benchmark:v0.0.1`.

## Execução ao vivo

Removendo o argumento `--headless`, o locust iniciará um servidor local e a URL fornecida pode ser aberta em um navegador para visualizar a execução ao vivo:

```bash
locust -f wms.py  --host https://ortos.dgterritorio.gov.pt/wms/ortoimagens2023  --random-seed 2776 --bbox-area 10000 --layer-name Ortoimagens2023-RGB  -u 10 -r 1 -t 2m --html reports/ortoimagens2023_u10_r1_t2_s2776.html  --loglevel INFO
[2024-04-26 15:45:46,525] moura002/INFO/locust.main: Starting web interface at http://0.0.0.0:8089
[2024-04-26 15:45:46,534] moura002/INFO/locust.main: Starting Locust 2.24.1
```

Copy paste `http://0.0.0.0:8089` into browser
Nota: Se o comando esta a correr no docker temos de abir os portos durante `docker run` por exemplo `-p8089:8089`.

## DGT WMTS

Lista de URLs e informações de camadas:

| Name | URL |layer | TileMatrixSet | Proj| TileMatrix |
|:----:|:---:|:----:|:-------------:|:---:|:-----------|
|Ortos 2021 Portugal-Continente (Mapproxy)| [https://cartografia.dgterritorio.gov.pt/ortos2021/service?service=wmts&request=getcapabilities](https://cartografia.dgterritorio.gov.pt/ortos2021/service?service=wmts&request=getcapabilities)| Ortos2021-RGB| PTTM_06| EPSG:3763  | 9325x16384 |
|Areas edificadas (Geoserver)| [https://geo2.dgterritorio.gov.pt/geoserver/AE/gwc/service/wmts?service=wmts&request=getcapabilities](https://geo2.dgterritorio.gov.pt/geoserver/AE/gwc/service/wmts?service=wmts&request=getcapabilities)| AE-Interface_Estrutural_2018 | EPSG:3857 | EPSG:3857 | (140/31542,463/15683) |
| PDOK luchtfoto 2023 |[https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0?service=wmts&request=getcapabilities]([https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0?service=wmts&request=getcapabilities) | Actueel_orthoHR|EPSG:28992/10  |EPSG:28992 | 1024x1024 |

## WMTS de terceiros

| Name | URL |layer | Proj |  BBOX |
|:----:|:---:|:----:|:----:|:-----:|
|Carta do Regime de Uso do Solo - Portugal Continental| [https://servicos.dgterritorio.pt/SDISNITWMSCRUS/WMService.aspx?service=wmts&request=getcapabilities](https://servicos.dgterritorio.pt/SDISNITWMSCRUS/WMService.aspx?service=wmts&request=getcapabilities) |CRUS| EPSG:3763|minx="-325383.32" miny="-317959.32" maxx="369324.95" maxy="293637.73"|
|PDOK luchtfoto 2023 | [https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0?service=wmts&request=getcapabilities](https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0?service=wmts&request=getcapabilities) | Actueel_orthoHR |EPSG:28992|  minx="-2000.0" miny="290000.0" maxx="294000.0" maxy="630000.0" |

## Debug do código

Atualmente, não há código pytest para teste, mas há código prototipo na seccao  `__main__` de cada script. As seguintes linhas podem ser ajustadas para testar o script, com esses links padrão:

```python
wmts_benchmark.host="https://cartografia.dgterritorio.gov.pt/ortos2021/service"
env.parsed_options.tile_random_seed = 1234
env.parsed_options.layer_name = "Ortos2021-RGB"
env.parsed_options.tile_matrix_set = "PTTM_06" # Most extreme case
env.parsed_options.tile_matrix = "07"
```

Nota: Os valores dos atributos são conforme a estrutura de linha de comando do locust.

Para executar os testes: `python wmts.py`.