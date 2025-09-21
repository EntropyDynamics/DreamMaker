Parte 2: Os Dados - A Matéria-Prima para Alphas
A qualidade de um sistema de HFT é diretamente proporcional à qualidade dos seus dados e das features extraídas deles. Para o Mini Índice, os dados mais ricos vêm do livro de ofertas (LOB).
2.1. Estrutura de Dados Essencial: O Limit Order Book (LOB)
O LOB é uma lista dinâmica de todas as ordens de compra (bid) e venda (ask) pendentes para um ativo, organizadas por nível de preço. É a representação mais granular da oferta e da demanda.
• Componentes Chave:
    ◦ Best Bid/Ask: O preço de compra mais alto e o preço de venda mais baixo disponíveis.
    ◦ Spread: A diferença entre o best ask e o best bid. É um indicador de liquidez e custo de transação.
    ◦ Profundidade (Depth): O volume de ordens disponíveis em cada nível de preço.
    ◦ Mid-Price: A média entre o best bid e o best ask, frequentemente usado como uma estimativa do "preço justo" momentâneo.
Via MT5, você terá acesso a esses dados em tempo real para o Mini Índice. O desafio é processar essa corrente de eventos (novas ordens, cancelamentos, negócios) de forma eficiente.
2.2. Amostragem Sincronizada por Informação: Lidando com o Ruído
Dados de mercado não chegam em intervalos de tempo regulares. Períodos de alta atividade são seguidos por calmaria. Usar barras de tempo fixas (ex: 1 minuto) é uma má prática em HFT, pois superamostra períodos lentos e subamostra períodos rápidos, destruindo propriedades estatísticas valiosas.
A solução é usar barras sincronizadas por informação:
• Tick Bars: Agrupar transações em "barras" de N ticks (negócios).
• Volume Bars: Agrupar transações até que um certo volume total seja negociado.
• Dollar Bars: Agrupar transações até que um certo valor financeiro total seja negociado.
Essas barras se adaptam à atividade do mercado, resultando em séries temporais com propriedades estatísticas melhores (retornos mais próximos de uma distribuição normal, menor autocorrelação), o que é ideal para modelos de ML.
2.3. Engenharia de Features (Identificação de Alphas)
Este é o processo de transformar os dados brutos do LOB em preditores significativos. Os "alphas" são esses preditores. Os documentos fornecem uma base rica para a criação de features de microestrutura.
• Order Flow Imbalance (OFI): Uma das features mais poderosas. Mede o desequilíbrio entre o fluxo de ordens de compra e venda nos melhores níveis do book. Um OFI positivo indica pressão compradora, e vice-versa. Sua fórmula captura mudanças no volume em resposta a movimentos de preço. Estudos mostram que o OFI tem forte poder preditivo sobre os movimentos de preço de curto prazo.
• Micro-preço (Micro-price): Uma estimativa mais robusta do preço justo do que o mid-price, pois pondera o best bid e o best ask pelo volume em cada lado. A fórmula é MicroPrice = (BestBid * AskVolume + BestAsk * BidVolume) / (BidVolume + AskVolume). Ele captura a pressão da liquidez no topo do book.
• Spread e Volatilidade: O spread (diferença entre best ask e best bid) como percentual do mid-price é um indicador de liquidez e custo. A volatilidade de curtíssimo prazo, calculada a partir dos ticks, mede o risco.
• Outras Features de Microestrutura: Incluem desequilíbrio de fila (queue imbalance), taxas de cancelamento de ordens e a inclinação do LOB (diferença de preço entre níveis de profundidade).
• Diferenciação Fracionária (Fractional Differentiation): Uma técnica avançada para tornar as séries temporais de features estacionárias (uma premissa para muitos modelos de ML) sem apagar toda a sua "memória" (autocorrelação), como a diferenciação inteira (cálculo de retornos) faz. Isso pode preservar mais poder preditivo.
Com este guia inicial sobre a arquitetura e o tratamento de dados, você tem o esqueleto do seu sistema de HFT. Cobrimos o "o quê" e o "porquê" das decisões de alto nível.