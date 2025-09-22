

# **Guia de Arquitetura e Implementação para Integração do MetaTrader 5 em Ambientes Linux com WSL e GitHub Actions**

## **Seção 1: Arquitetando a Solução Multiplataforma para o MetaTrader 5**

Esta seção estabelece a base conceitual para a integração do pacote Python do MetaTrader 5 em um fluxo de trabalho baseado em Linux. A análise aprofundada do problema, das restrições técnicas e da arquitetura da solução proposta fornecerá um roteiro claro para as etapas de implementação subsequentes.

### **1.1 O Desafio Central: Uma Dependência do Windows em um Mundo Linux**

O desafio fundamental reside na incompatibilidade de sistema operacional do pacote MetaTrader5 para Python. Uma análise detalhada revela que este pacote não é uma biblioteca autônoma, mas sim um conector de API que depende da comunicação entre processos (IPC) com uma instância em execução do terminal MetaTrader 5\.1 O terminal, por sua vez, é uma aplicação nativa do Windows.

A confirmação dessa dependência é encontrada na própria distribuição do pacote no Python Package Index (PyPI). Os arquivos disponíveis para download são exclusivamente *wheels* do Windows (com a tag win\_amd64.whl), o que impede a sua instalação direta em qualquer distribuição Linux através de um simples comando pip install.4 Portanto, a tarefa não se resume a executar um script Python, mas a criar um ambiente emulado capaz de hospedar o ecossistema completo do MetaTrader 5 e, ao mesmo tempo, interagir com processos nativos do Linux.

### **1.2 O Blueprint Arquitetônico: Uma Pilha de Emulação e Comunicação em Múltiplas Camadas**

Para superar a barreira do sistema operacional, é necessária uma arquitetura em múltiplas camadas que gerencie a emulação e a comunicação entre os ambientes Windows e Linux. A solução proposta opera através de uma cadeia de componentes interconectados, onde cada um desempenha um papel específico para preencher a lacuna de compatibilidade.

O fluxo de comunicação pode ser visualizado da seguinte forma:

1. O script Python do usuário, executado no ambiente Linux (WSL ou GitHub Actions), inicia uma chamada de função (por exemplo, mt5.initialize()).  
2. Essa chamada é interceptada por um cliente de Chamada de Procedimento Remoto (RPyC), fornecido por uma biblioteca de wrapper como a pymt5linux.  
3. O cliente RPyC serializa a chamada e a envia através de um soquete de rede local para um servidor RPyC correspondente.  
4. O servidor RPyC, que está em execução dentro de um ambiente Python para Windows emulado, recebe a chamada.  
5. Este servidor, por sua vez, invoca a função real no pacote MetaTrader5 instalado nesse ambiente emulado.  
6. O pacote MetaTrader5 comunica-se com o terminal MetaTrader 5 através dos mecanismos de IPC nativos do Windows.  
7. O terminal MT5, sendo uma aplicação com interface gráfica (GUI), não pode ser executado em um ambiente de servidor sem cabeça (*headless*) sem um display. Para resolver isso, ele renderiza sua interface em um framebuffer virtual fornecido pelo Xvfb.

Esta arquitetura, embora complexa, é robusta e permite que um processo nativo do Linux controle e extraia dados de uma aplicação nativa do Windows de forma transparente, desde que cada camada esteja configurada corretamente. A complexidade inerente a esta pilha de comunicação destaca a importância de uma abordagem de encapsulamento, como o Docker, para garantir a reprodutibilidade e a estabilidade, especialmente em ambientes de automação.

### **1.3 Tecnologias Chave e Seus Papéis**

A implementação bem-sucedida da arquitetura descrita depende da orquestração de várias tecnologias de código aberto. Cada uma delas é uma peça indispensável no quebra-cabeça da interoperabilidade.

* **Wine**: É a camada de compatibilidade que permite a execução de aplicações binárias do Windows diretamente em sistemas operacionais do tipo Unix, como o Linux. No contexto desta solução, o Wine é usado para executar tanto o terminal MetaTrader 5 quanto uma instalação completa do Python para Windows.5  
* **Xvfb (X Virtual Framebuffer)**: Uma ferramenta crítica que implementa o protocolo de servidor de exibição X11 em memória, sem exibir qualquer saída em tela. O Xvfb cria um display virtual que permite que aplicações GUI, como o terminal MT5, sejam executadas em um ambiente de servidor *headless* (sem monitor), como um contêiner Docker ou um executor do GitHub Actions.7 Sem o Xvfb, o terminal MT5 falharia ao iniciar, interrompendo toda a cadeia de comunicação.  
* **Wrappers RPyC (Remote Python Call)**: Bibliotecas como mt5linux e seu fork mais moderno, pymt5linux, fornecem a ponte de comunicação essencial entre o ambiente Python do Linux e o ambiente Python emulado pelo Wine. Elas implementam um modelo cliente-servidor que expõe a API do MetaTrader5 através de uma interface de rede, permitindo que o código Linux invoque funções como se estivessem sendo executadas localmente.5  
* **Docker**: A tecnologia de contêinerização que encapsula toda a complexa pilha de software (Linux, Wine, Xvfb, Python para Windows, terminal MT5 e scripts de servidor) em uma única imagem portátil e reprodutível. O Docker transforma a configuração manual e propensa a erros em um artefato de infraestrutura como código, que é a chave para a automação confiável.7  
* **GitHub Actions**: A plataforma de Integração Contínua e Entrega Contínua (CI/CD) que automatiza o fluxo de trabalho. Ela será usada para construir a imagem Docker, executá-la como um serviço em segundo plano e, em seguida, executar os scripts Python do usuário que interagem com o ambiente MT5 contido na imagem.13

## **Seção 2: Configuração do Ambiente de Desenvolvimento Local no WSL**

Antes de automatizar o processo de implantação, é fundamental estabelecer um ambiente de desenvolvimento local funcional. O Subsistema Windows para Linux (WSL) é a plataforma ideal para replicar a arquitetura de destino, permitindo o desenvolvimento e o teste rápidos do código da aplicação. Esta seção detalha o processo manual de configuração de todos os componentes necessários no WSL.

### **2.1 Preparando a Fundação: Instalando Wine e Xvfb**

Os primeiros passos envolvem a instalação dos pacotes Linux fundamentais que fornecerão a camada de emulação e o display virtual. Em uma distribuição WSL baseada em Debian/Ubuntu, esses componentes podem ser instalados com um único comando no terminal.

Bash

sudo apt update && sudo apt install wine xvfb \-y

A instalação do Wine cria a estrutura de diretórios necessária para simular um sistema de arquivos do Windows (geralmente em \~/.wine/drive\_c), enquanto o Xvfb fornece o utilitário xvfb-run, que será usado para iniciar aplicações GUI em um ambiente sem monitor.6

### **2.2 Instalando o MetaTrader 5 e o Python para Windows sob o Wine**

Com a camada de emulação pronta, o próximo passo é instalar o software específico do Windows. Isso inclui o terminal MetaTrader 5 e uma versão do Python para Windows que seja compatível com o pacote MetaTrader5.

1. **Download dos Instaladores**: Faça o download do instalador oficial do MetaTrader 5 e de um instalador do Python para Windows (por exemplo, a versão 3.8, que é frequentemente citada como compatível em guias da comunidade).6 Use comandos como  
   wget diretamente no terminal WSL.  
   Bash  
   \# Exemplo para Python 3.8  
   wget https://www.python.org/ftp/python/3.8.0/python-3.8.0-amd64.exe  
   \# Download do instalador do MT5  
   wget https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe

2. **Execução dos Instaladores com Wine**: Use o comando wine para executar os instaladores. O Wine abrirá as janelas de instalação do Windows, que podem ser interagidas normalmente.  
   Bash  
   wine python-3.8.0-amd64.exe  
   wine mt5setup.exe

Durante a instalação do Python para Windows, é de suma importância marcar a opção "Add Python 3.8 to PATH". Esta ação configura a variável de ambiente PATH dentro do registro do Wine, o que simplifica enormemente a execução de comandos Python no prompt de comando do Wine (wine cmd) e evita a necessidade de edições manuais complexas no registro.1

### **2.3 Conectando os Ambientes com pymt5linux**

A comunicação entre o script Python no WSL (Linux) e o pacote MetaTrader5 no Wine (Windows) requer uma biblioteca de ponte. Embora mt5linux tenha sido o pacote original para essa finalidade, pymt5linux é um fork mais recente e ativamente mantido, oferecendo melhor compatibilidade com atualizações recentes do MT5 e versões mais novas do Python.10

| Característica | mt5linux 5 | pymt5linux 10 | Justificativa da Escolha |
| :---- | :---- | :---- | :---- |
| **Origem** | Pacote original | Fork do mt5linux | pymt5linux se baseia no conceito original. |
| **Último Lançamento** | Março de 2022 | Mantido ativamente | A manutenção ativa é crucial para a compatibilidade com as atualizações do MT5. |
| **Suporte a Python** | Versões mais antigas (ex: 3.8) | Atualizado para versões modernas (ex: 3.13) | Garante a longevidade e a compatibilidade futura do projeto. |
| **Recomendação** | Descontinuado | **Recomendado** | A escolha clara para um novo projeto. |

A instalação deve ser feita em ambos os ambientes, pois a biblioteca possui componentes de cliente e servidor:

1. **No terminal WSL (ambiente Linux)**: Instale o cliente.  
   Bash  
   pip install pymt5linux

2. **No prompt de comando do Wine (ambiente Windows)**: Instale o servidor e a dependência MetaTrader5.  
   Bash  
   wine cmd  
   \# Dentro do prompt do Wine  
   python \-m pip install MetaTrader5 pymt5linux

Esta instalação dupla é necessária porque o script no Linux atuará como o cliente, enquanto o script dentro do Wine atuará como o servidor que tem acesso direto à API do MetaTrader5.10

### **2.4 Um Teste Prático: Validando a Configuração Local**

Para validar se todas as camadas estão funcionando em conjunto, execute a seguinte sequência de comandos em terminais WSL separados:

1. **Terminal 1: Inicie o Terminal MT5 com Xvfb**. O comando xvfb-run cria o display virtual, e o & executa o processo em segundo plano.  
   Bash  
   \# O caminho pode variar dependendo da sua instalação  
   xvfb-run wine "/home/USER/.wine/drive\_c/Program Files/MetaTrader 5/terminal64.exe" &

2. **Terminal 2: Inicie o Servidor RPyC no Wine**. Este comando inicia o servidor de escuta que aguardará as conexões do cliente Linux.  
   Bash  
   \# O caminho para o python.exe do Wine pode variar  
   wine cmd /c "python \-m pymt5linux /home/USER/.wine/drive\_c/users/USER/Local\\ Settings/Application\\ Data/Programs/Python/Python38/python.exe"

3. **Terminal 3: Execute o Script Cliente no WSL**. Crie um arquivo Python (ex: test\_connection.py) no seu ambiente WSL com o seguinte conteúdo e execute-o.  
   Python  
   \# test\_connection.py  
   from pymt5linux import MetaTrader5  
   import time

   print("Tentando conectar ao MT5...")  
   \# Inicializa a conexão com o servidor RPyC  
   mt5 \= MetaTrader5(host="localhost", port=18812) \# Porta padrão para mt5linux/pymt5linux

   if not mt5.initialize():  
       print(f"initialize() falhou, código de erro \= {mt5.last\_error()}")  
       mt5.shutdown()  
   else:  
       print("Conexão bem-sucedida\!")  
       terminal\_info \= mt5.terminal\_info()  
       if terminal\_info:  
           print(f"Conectado a {terminal\_info.name}")  
       else:  
           print("Falha ao obter informações do terminal.")

       \# Não se esqueça de encerrar a conexão  
       mt5.shutdown()  
       print("Conexão encerrada.")

   Execute o script:  
   Bash  
   python3 test\_connection.py

Se a saída indicar "Conexão bem-sucedida\!", a configuração local está validada. Este processo manual, embora funcional para o desenvolvimento, é frágil e propenso a erros de configuração de caminhos e versões. Ele demonstra claramente a necessidade de automação e encapsulamento, que serão abordados na próxima seção com o Docker.

## **Seção 3: Encapsulamento para Portabilidade: A Estratégia Docker**

A configuração manual detalhada na seção anterior, embora útil para o desenvolvimento local, não é adequada para um ambiente de implantação automatizado e confiável. A solução para isso é o encapsulamento de toda a pilha de software em uma imagem Docker. Esta abordagem transforma a configuração complexa e dependente da máquina em um artefato imutável e portátil de infraestrutura como código, que é a base para a automação com o GitHub Actions.

### **3.1 Projetando o Dockerfile Definitivo**

O Dockerfile é a receita para construir a imagem. Ele automatizará cada etapa realizada manualmente na Seção 2, garantindo que o ambiente seja idêntico em qualquer máquina que execute o Docker. O Dockerfile a seguir é uma implementação robusta, inspirada em práticas comuns para executar aplicações Windows com Wine e Xvfb em contêineres.7

Dockerfile

\# Use uma base Linux estável  
FROM ubuntu:22.04

\# Evita prompts interativos durante a instalação de pacotes  
ENV DEBIAN\_FRONTEND=noninteractive

\# Instala dependências essenciais: Wine, Xvfb, ferramentas de download e outros utilitários  
RUN apt-get update && \\  
    apt-get install \-y \--no-install-recommends \\  
    wine \\  
    xvfb \\  
    wget \\  
    cabextract \\  
    unzip \\  
    ca-certificates && \\  
    rm \-rf /var/lib/apt/lists/\*

\# Define o ambiente do Wine  
ENV WINEARCH=win64  
ENV WINEPREFIX=/root/.wine

\# Inicializa o ambiente Wine  
RUN winecfg

\# Baixa e instala o Python para Windows (ex: 3.8.10)  
RUN wget https://www.python.org/ftp/python/3.8.10/python-3.8.10-amd64.exe \-O /tmp/python\_installer.exe && \\  
    xvfb-run wine /tmp/python\_installer.exe /quiet InstallAllUsers=1 PrependPath=1 && \\  
    rm /tmp/python\_installer.exe

\# Define o caminho para o Python do Wine para facilitar o uso  
ENV WINE\_PYTHON\_PATH="/root/.wine/drive\_c/Program Files/Python38/python.exe"

\# Baixa e instala o terminal MetaTrader 5  
RUN wget https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe \-O /tmp/mt5setup.exe && \\  
    xvfb-run wine /tmp/mt5setup.exe /auto && \\  
    rm /tmp/mt5setup.exe

\# Define o caminho para o terminal MT5  
ENV MT5\_TERMINAL\_PATH="/root/.wine/drive\_c/Program Files/MetaTrader 5/terminal64.exe"

\# Instala as bibliotecas Python necessárias no ambiente Wine  
RUN wine "${WINE\_PYTHON\_PATH}" \-m pip install \--upgrade pip && \\  
    wine "${WINE\_PYTHON\_PATH}" \-m pip install MetaTrader5 pymt5linux

\# Copia um script de inicialização para dentro do contêiner  
COPY start.sh /start.sh  
RUN chmod \+x /start.sh

\# Expõe a porta do servidor RPyC  
EXPOSE 18812

\# Define o comando de inicialização do contêiner  
CMD \["/start.sh"\]

O script start.sh, que deve ser criado no mesmo diretório do Dockerfile, orquestra o lançamento dos processos dentro do contêiner:

Bash

\#\!/bin/bash

\# Inicia o Xvfb em segundo plano no display :99  
Xvfb :99 \-screen 0 1024x768x16 &  
export DISPLAY=:99

\# Aguarda o Xvfb iniciar  
sleep 5

\# Inicia o terminal MetaTrader 5 em segundo plano  
echo "Iniciando MetaTrader 5 Terminal..."  
wine "${MT5\_TERMINAL\_PATH}" &  
MT5\_PID=$\!

\# Aguarda o terminal iniciar  
sleep 15

\# Inicia o servidor RPyC em primeiro plano  
echo "Iniciando servidor RPyC..."  
wine "${WINE\_PYTHON\_PATH}" \-m pymt5linux "${WINE\_PYTHON\_PATH}"

\# Mantém o contêiner em execução e gerencia o encerramento  
wait $MT5\_PID

### **3.2 Construindo e Executando o Ambiente MT5 Contêinerizado**

Com o Dockerfile e o start.sh prontos, a construção da imagem e a execução do contêiner são realizadas com comandos Docker padrão:

1. **Construir a Imagem**: Navegue até o diretório que contém os arquivos e execute o comando build. A tag \-t mt5-environment nomeia a imagem para referência futura.  
   Bash  
   docker build \-t mt5-environment.

2. **Executar o Contêiner**: Inicie o contêiner a partir da imagem recém-construída.  
   Bash  
   docker run \-d \-p 18812:18812 \--name mt5\_container mt5-environment

   * \-d: Executa o contêiner em modo desanexado (*detached*), ou seja, em segundo plano.  
   * \-p 18812:18812: Mapeia a porta 18812 do contêiner (onde o servidor RPyC está escutando) para a porta 18812 da máquina hospedeira (seu WSL). Isso torna o servidor acessível de fora do contêiner.11  
   * \--name mt5\_container: Atribui um nome amigável ao contêiner para facilitar o gerenciamento.

### **3.3 Validando o Contêiner**

A validação final consiste em executar o mesmo script cliente test\_connection.py da Seção 2.4 a partir do seu terminal WSL. Desta vez, o script não se conectará aos processos em execução direta no WSL, mas sim ao servidor RPyC que está em execução dentro do contêiner Docker, através da porta mapeada localhost:18812.

Se o script for executado com sucesso, isso prova que o encapsulamento foi bem-sucedido. A pilha complexa do MetaTrader 5 agora existe como um artefato de software autônomo e portátil. Para depurar problemas de inicialização dentro do contêiner, o comando docker logs mt5\_container é essencial, pois exibirá a saída do script start.sh.

Esta imagem Docker é o pilar que possibilita a automação CI/CD, pois pode ser executada de forma consistente e previsível em qualquer ambiente que suporte o Docker, incluindo os executores do GitHub Actions.

## **Seção 4: Automação Completa com GitHub Actions**

Com um artefato Docker portátil e confiável em mãos, o passo final é automatizar o processo de teste e implantação usando o GitHub Actions. Esta seção descreve como construir um pipeline de CI/CD que utiliza a imagem Docker para criar um ambiente MT5 sob demanda, executar o código da aplicação e garantir a integração contínua.

### **4.1 Estratégia de Fluxo de Trabalho: O Padrão de Contêiner de Serviço**

O GitHub Actions oferece um recurso poderoso chamado "contêineres de serviço" (*service containers*), que é perfeitamente adequado para este caso de uso. Um contêiner de serviço é uma imagem Docker que é iniciada em segundo plano no início de um trabalho e fica disponível para os passos principais do trabalho através da rede. O executor do GitHub Actions gerencia o ciclo de vida do contêiner de serviço, iniciando-o antes da execução dos scripts e encerrando-o ao final do trabalho.13

Nesta arquitetura, a imagem mt5-environment será executada como um contêiner de serviço. Os passos principais do trabalho (por exemplo, a execução do script Python do usuário) se conectarão a este serviço na rede interna do Docker gerenciada pelo GitHub Actions.

### **4.2 Criando o Fluxo de Trabalho do GitHub Actions (arquivo .yml)**

O fluxo de trabalho é definido em um arquivo YAML localizado no diretório .github/workflows/ do repositório. O exemplo a seguir define um pipeline de dois trabalhos: o primeiro constrói e envia a imagem Docker para um registro (como o GitHub Container Registry \- GHCR), e o segundo utiliza essa imagem como um serviço para executar testes.

YAML

\#.github/workflows/main.yml  
name: Pipeline de CI do MT5 Python

on:  
  push:  
    branches: \[ main \]  
  workflow\_dispatch: \# Permite a execução manual do workflow \[16\]

jobs:  
  \# Trabalho 1: Construir e publicar a imagem Docker  
  build-and-push-image:  
    runs-on: ubuntu-latest  
    permissions:  
      contents: read  
      packages: write \# Permissão para enviar pacotes (imagens) para o GHCR  
      
    steps:  
      \- name: Checkout do repositório  
        uses: actions/checkout@v4

      \- name: Login no GitHub Container Registry  
        uses: docker/login-action@v3  
        with:  
          registry: ghcr.io  
          username: ${{ github.actor }}  
          password: ${{ secrets.GITHUB\_TOKEN }}

      \- name: Construir e enviar imagem Docker  
        uses: docker/build-push-action@v5  
        with:  
          context:.  
          push: true  
          tags: ghcr.io/${{ github.repository }}/mt5-environment:latest

  \# Trabalho 2: Executar testes usando a imagem como serviço  
  run-mt5-tests:  
    needs: build-and-push-image \# Depende da conclusão do trabalho anterior  
    runs-on: ubuntu-latest

    services:  
      \# Define o contêiner de serviço  
      mt5:  
        image: ghcr.io/${{ github.repository }}/mt5-environment:latest  
        ports:  
          \- 18812:18812 \# Mapeia a porta para o host do executor  
        credentials:  
          username: ${{ github.actor }}  
          password: ${{ secrets.GITHUB\_TOKEN }}

    steps:  
      \- name: Checkout do repositório  
        uses: actions/checkout@v4

      \- name: Configurar Python  
        uses: actions/setup-python@v5  
        with:  
          python-version: '3.9'

      \- name: Instalar dependências Python  
        run: pip install pymt5linux pandas

      \- name: Executar script da aplicação  
        env:  
          \# Injeta credenciais de forma segura a partir dos segredos do repositório  
          MT5\_LOGIN: ${{ secrets.MT5\_LOGIN }}  
          MT5\_PASSWORD: ${{ secrets.MT5\_PASSWORD }}  
          MT5\_SERVER: ${{ secrets.MT5\_SERVER }}  
        \# O script se conectará a 'localhost:18812' devido ao mapeamento de portas  
        run: python your\_main\_script.py

A tabela a seguir detalha a lógica por trás de cada seção chave do fluxo de trabalho.

| Seção do Fluxo de Trabalho | Sintaxe Chave | Justificativa e Explicação |
| :---- | :---- | :---- |
| **Gatilho** | on: \[push, workflow\_dispatch\] | Executa o fluxo de trabalho automaticamente em cada push para a branch main e permite o acionamento manual a partir da interface do GitHub.15 |
| **Trabalho 1: Construção** | jobs: build-and-push-image | Um trabalho dedicado para construir a imagem Docker. Isso separa a criação do ambiente da lógica da aplicação, promovendo a reutilização da imagem. |
| **Dependência de Trabalho** | needs: build-and-push-image | Garante que o trabalho de teste só seja executado após a imagem Docker ter sido construída e enviada com sucesso para um registro. |
| **Contêiner de Serviço** | services: mt5: image:... | O núcleo da solução. O GitHub Actions inicia o contêiner MT5 em segundo plano antes da execução dos passos. Ele é acessível na rede através do nome de host mt5. |
| **Mapeamento de Portas** | ports: \- 18812:18812 | Expõe a porta RPyC do contêiner de serviço para o host do executor, permitindo que o script Python se conecte via localhost:18812. |
| **Gerenciamento de Segredos** | env: MT5\_LOGIN: ${{ secrets.MT5\_LOGIN }} | Injeta credenciais sensíveis no ambiente do trabalho de forma segura, utilizando o armazenamento criptografado de segredos do GitHub e evitando a exposição de senhas no código.17 |

### **4.3 Gerenciamento Seguro de Credenciais**

A segurança das credenciais de negociação é de extrema importância. O GitHub Actions fornece um mecanismo seguro para gerenciar informações sensíveis, como logins, senhas e nomes de servidores, através dos "Segredos" (*Secrets*).

Para configurar os segredos:

1. Navegue até o seu repositório no GitHub.  
2. Vá para Settings \> Secrets and variables \> Actions.  
3. Clique em New repository secret para cada credencial que você precisa armazenar (ex: MT5\_LOGIN, MT5\_PASSWORD, MT5\_SERVER).  
4. Adicione os valores correspondentes. Esses valores são criptografados e só podem ser acessados por fluxos de trabalho do GitHub Actions.

Esta abordagem garante que as credenciais nunca sejam armazenadas em texto plano no código do repositório, seguindo as melhores práticas de segurança.17

## **Seção 5: Considerações Avançadas e Melhores Práticas**

A implementação de uma solução baseada em emulação e múltiplas camadas de comunicação, como a descrita, é uma façanha técnica que resolve um problema complexo. No entanto, é crucial compreender suas nuances, limitações e as alternativas disponíveis para tomar decisões de arquitetura informadas e garantir a estabilidade do sistema em produção.

### **5.1 Desempenho, Estabilidade e Depuração**

* **Desempenho**: A arquitetura introduz uma latência inerente devido às múltiplas camadas que uma solicitação deve atravessar: a ponte RPyC (serialização/desserialização de dados e comunicação de rede) e a camada de emulação do Wine. Consequentemente, esta solução é mais adequada para estratégias de negociação de média a baixa frequência, coleta periódica de dados, geração de sinais ou gerenciamento de risco. Não é recomendada para aplicações de negociação de alta frequência (HFT) onde a latência de microssegundos é crítica.  
* **Estabilidade**: O terminal MetaTrader 5 foi projetado como uma aplicação de desktop para o usuário final, não como um serviço de servidor para operação contínua e não supervisionada. Ele pode apresentar instabilidade, vazamentos de memória ou travamentos durante longos períodos de execução. Para mitigar isso, é altamente recomendável usar um gerenciador de processos como o supervisor dentro do contêiner Docker. O supervisor pode ser configurado para monitorar o processo do terminal64.exe e do servidor RPyC, reiniciando-os automaticamente em caso de falha, o que aumenta significativamente a resiliência do sistema.7  
* **Depuração**: A depuração de um sistema com tantas camadas pode ser desafiadora. Uma abordagem metódica é essencial:  
  1. **Logs do Contêiner Docker**: Verifique os logs do contêiner (docker logs \<container\_name\>) para erros de inicialização no script start.sh, no Xvfb ou no Wine.  
  2. **Logs do Terminal MT5**: Configure o contêiner para montar um volume (-v) que aponte para o diretório de logs do MetaTrader 5 dentro do WINEPREFIX. Isso permite a inspeção dos logs do terminal (Journal/) a partir da máquina hospedeira.  
  3. **Logs da Aplicação**: Adicione registros detalhados (logging) tanto no script do servidor RPyC (dentro do start.sh) quanto no script do cliente Python para rastrear o fluxo de solicitações e respostas.  
  4. **Acesso Interativo**: Use docker exec \-it \<container\_id\> /bin/bash para obter um shell interativo dentro do contêiner em execução. Isso permite a verificação do status dos processos, a exploração do sistema de arquivos e a execução de comandos de diagnóstico em tempo real.

### **5.2 Arquitetura Alternativa: O Executor Auto-Hospedado do Windows**

Uma alternativa que contorna completamente a complexidade da emulação (Wine, Xvfb, Docker) é o uso de um executor auto-hospedado (*self-hosted runner*) do GitHub Actions.17

* **Conceito**: Em vez de usar os executores Linux fornecidos pelo GitHub, é possível configurar uma máquina própria (física ou virtual) para executar os trabalhos do GitHub Actions. Ao instalar o software do executor em uma máquina com Windows Server ou Windows 10/11, cria-se um ambiente nativo para o MetaTrader 5\.19  
* **Implementação**: O fluxo de trabalho do GitHub Actions seria drasticamente simplificado. Ele especificaria runs-on: self-hosted-windows e executaria diretamente os comandos de instalação de dependências Python e o script da aplicação, sem a necessidade de Docker ou Wine.21  
* **Análise de Trade-offs**:  
  * **Vantagens do Executor Auto-Hospedado do Windows**:  
    * **Simplicidade**: A configuração é muito mais direta, eliminando múltiplas camadas de emulação e comunicação.  
    * **Desempenho**: A execução nativa elimina a sobrecarga do Wine e da comunicação de rede RPyC, resultando em maior desempenho e menor latência.  
    * **Compatibilidade**: Elimina os riscos de incompatibilidade entre as versões do Wine e as atualizações do MetaTrader 5\.  
  * **Desvantagens do Executor Auto-Hospedado do Windows**:  
    * **Gerenciamento de Infraestrutura**: A responsabilidade pela manutenção, atualização, correção de segurança e monitoramento do sistema operacional Windows recai sobre o usuário.  
    * **Custo**: Há custos associados à manutenção de uma máquina ou VM Windows funcionando 24/7.  
    * **Portabilidade e Escalabilidade**: A solução está atrelada a uma máquina específica, tornando-a menos portátil e mais difícil de escalar em comparação com contêineres Docker, que podem ser implantados em qualquer provedor de nuvem.  
    * **Paradigma de Infraestrutura**: Afasta-se do paradigma moderno de infraestrutura como código, onde todo o ambiente é definido em arquivos de texto (Dockerfile, .yml) e é totalmente reprodutível.

## **Conclusões**

A integração do pacote Python do MetaTrader 5 em um fluxo de trabalho baseado em Linux é um desafio significativo, mas solucionável através de uma arquitetura de emulação e comunicação cuidadosamente projetada.

A solução principal, baseada em **Docker, Wine, Xvfb e RPyC**, representa uma abordagem de engenharia robusta que adere aos princípios modernos de DevOps. Ela produz um artefato **portátil, reprodutível e totalmente automatizável** através do GitHub Actions. Embora sua complexidade exija uma implementação cuidadosa e estratégias de depuração, ela oferece a máxima flexibilidade e alinhamento com ecossistemas nativos da nuvem, sendo a escolha recomendada para projetos que valorizam a infraestrutura como código e a implantação agnóstica de plataforma.

Por outro lado, a arquitetura alternativa utilizando um **executor auto-hospedado do Windows** oferece um caminho de **menor complexidade e maior desempenho nativo**. Esta é uma opção pragmática e viável para indivíduos ou equipes que já gerenciam infraestrutura Windows ou que priorizam a simplicidade de implementação em detrimento da portabilidade e dos paradigmas de contêinerização.

A escolha final entre as duas arquiteturas depende de um balanço entre os requisitos do projeto, as competências técnicas da equipe e as restrições de infraestrutura. Este relatório fornece os blueprints detalhados e a análise de trade-offs necessários para tomar essa decisão de forma informada e implementar com sucesso a solução escolhida.

#### **Referências citadas**

1. Python Integration \- MQL5 Reference \- Reference on algorithmic/automated trading language for MetaTrader 5, acessado em setembro 21, 2025, [https://www.mql5.com/en/docs/python\_metatrader5](https://www.mql5.com/en/docs/python_metatrader5)  
2. How to interactive with MT5 with python | by Asc686f61 | Medium, acessado em setembro 21, 2025, [https://medium.com/@asc686f61/how-to-interactive-with-mt5-with-python-99053eedd067](https://medium.com/@asc686f61/how-to-interactive-with-mt5-with-python-99053eedd067)  
3. How to pull data from MetaTrader 5 with Python | by Eduardo Bogosian | Medium, acessado em setembro 21, 2025, [https://medium.com/@eduardo-bogosian/how-to-pull-data-from-metatrader-5-with-python-4889bd92f62d](https://medium.com/@eduardo-bogosian/how-to-pull-data-from-metatrader-5-with-python-4889bd92f62d)  
4. MetaTrader5 \- PyPI, acessado em setembro 21, 2025, [https://pypi.org/project/MetaTrader5/](https://pypi.org/project/MetaTrader5/)  
5. mt5linux · PyPI, acessado em setembro 21, 2025, [https://pypi.org/project/mt5linux/](https://pypi.org/project/mt5linux/)  
6. A guide to successfully install MT5 and MetaTrader5 package for ..., acessado em setembro 21, 2025, [https://www.mql5.com/en/forum/457940](https://www.mql5.com/en/forum/457940)  
7. Use MT5 in Linux with Docker and Python | by Asc686f61 | Medium, acessado em setembro 21, 2025, [https://medium.com/@asc686f61/use-mt5-in-linux-with-docker-and-python-f8a9859d65b1](https://medium.com/@asc686f61/use-mt5-in-linux-with-docker-and-python-f8a9859d65b1)  
8. FragSoc/steamcmd-wine-xvfb-docker: A docker image to serve as a base for running windows-based gameservers in linux \- GitHub, acessado em setembro 21, 2025, [https://github.com/FragSoc/steamcmd-wine-xvfb-docker](https://github.com/FragSoc/steamcmd-wine-xvfb-docker)  
9. How to run headless unit tests for GUIs on GitHub actions \- Arbitrary but fixed, acessado em setembro 21, 2025, [https://arbitrary-but-fixed.net/2022/01/21/headless-gui-github-actions.html](https://arbitrary-but-fixed.net/2022/01/21/headless-gui-github-actions.html)  
10. pymt5linux \- PyPI Package Security Analysis \- Socket \- Socket.dev, acessado em setembro 21, 2025, [https://socket.dev/pypi/package/pymt5linux](https://socket.dev/pypi/package/pymt5linux)  
11. fortesenselabs/metatrader5-terminal \- Docker Image, acessado em setembro 21, 2025, [https://hub.docker.com/r/fortesenselabs/metatrader5-terminal](https://hub.docker.com/r/fortesenselabs/metatrader5-terminal)  
12. gmag11/MetaTrader5-Docker-Image: Docker image that runs Metatrader 5 with VNC web server \- GitHub, acessado em setembro 21, 2025, [https://github.com/gmag11/MetaTrader5-Docker-Image](https://github.com/gmag11/MetaTrader5-Docker-Image)  
13. Quickstart for GitHub Actions, acessado em setembro 21, 2025, [https://docs.github.com/en/actions/get-started/quickstart](https://docs.github.com/en/actions/get-started/quickstart)  
14. GitHub Actions, acessado em setembro 21, 2025, [https://github.com/features/actions](https://github.com/features/actions)  
15. Manually running a workflow \- GitHub Docs, acessado em setembro 21, 2025, [https://docs.github.com/actions/managing-workflow-runs/manually-running-a-workflow](https://docs.github.com/actions/managing-workflow-runs/manually-running-a-workflow)  
16. Embedded Github Action UI \- RUNME, acessado em setembro 21, 2025, [https://docs.runme.dev/usage/embedded-github-action](https://docs.runme.dev/usage/embedded-github-action)  
17. Self-hosted runners \- GitHub Docs, acessado em setembro 21, 2025, [https://docs.github.com/actions/hosting-your-own-runners](https://docs.github.com/actions/hosting-your-own-runners)  
18. Setup GitHub Actions Self-Hosted Runner On VMs & Containers \- DevOpsCube, acessado em setembro 21, 2025, [https://devopscube.com/github-actions-self-hosted-runner/](https://devopscube.com/github-actions-self-hosted-runner/)  
19. Configuring the self-hosted runner application as a service \- GitHub Docs, acessado em setembro 21, 2025, [https://docs.github.com/actions/hosting-your-own-runners/managing-self-hosted-runners/configuring-the-self-hosted-runner-application-as-a-service](https://docs.github.com/actions/hosting-your-own-runners/managing-self-hosted-runners/configuring-the-self-hosted-runner-application-as-a-service)  
20. Adding self-hosted runners \- GitHub Docs, acessado em setembro 21, 2025, [https://docs.github.com/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners](https://docs.github.com/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners)  
21. Using self-hosted runners in a workflow \- GitHub Docs, acessado em setembro 21, 2025, [https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow)