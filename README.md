# AWS Machine Learning (ETL/NLP)

## Sobre o projeto

Este projeto tem como objetivo treinar um modelo de **Machine Learning** capaz de analisar frases de reviews e identificar:

* Se a review é **positiva** ou **negativa**.
* Os **tópicos** abordados na review.
* A **precisão** do modelo na classificação das reviews.

O fluxo de dados utiliza serviços da **AWS** para coletar, processar e treinar os dados, integrando uma **API** para receber as reviews, triggers automáticas para processamento e um modelo de ML para classificação.

---

## Tecnologias utilizadas

* **AWS S3** – armazenamento de dados.
* **AWS Lambda** – processamento e transformação dos dados.
* **AWS API Gateway** – disponibilização da API para envio de reviews.
* **AWS SageMaker** – treinamento e deploy do modelo de Machine Learning.
* **Terraform** – automação da infraestrutura na AWS.

---

## Estrutura do projeto

### API de Upload

A pasta `api_upload_csv` contém os scripts em **Terraform** para criar a infraestrutura necessária para receber as reviews via API.

**Endpoint:**
`POST https://i4oc8751ya.execute-api.us-east-1.amazonaws.com/`

**Formato esperado:**

```json
{
    "message": "Melhor compra da minha vida.",
    "score": 5
}
```

**Regras de validação:**

* `message` e `score` são obrigatórios
* `score` deve ser um número entre 1 e 5

**Processamento:**
* Cria (ou atualiza) um arquivo CSV diário em `raw/api/review/{YYYY-MM-DD}.csv`
* Se o arquivo já existir, a nova review é incluida

---

### Processamento de Dados

A pasta `process_data_lambda` contém o Terraform para provisionar uma **Lambda** responsável pelo tratamento dos dados brutos.

A função é acionada quando novos arquivos são adicionados ao S3, seja manualmente (`raw/manual/order_reviews/`) ou via API (`raw/api/review/`).

**Transformações aplicadas nos dados:**

* Ignora linhas sem comentário de review
* Remove quebras de linha
* Normaliza espaços em branco
* Aplica regra de negócio para negações:

  * Ex.: `"Não gostei"` → `"nao_gostei"`

Após o processamento, os dados são salvos em um arquivo CSV dentro de `processed/review/`, utilizando o nome do arquivo original acrescido do sufixo *_processed*.

---

### Treinamento do Modelo

A pasta `machine_learning` contém o código utilizado no **AWS SageMaker Studio** (JupyterLab) para treinar o modelo de classificação de reviews.

**Carregamento dos dados**

Os dados são extraídos do **Athena**, a partir do bucket `processed/review/`, filtrando apenas reviews com `score` diferente de 3. O motivo é que o score 3 representa uma avaliação neutra, que não contribui para treinar a máquina a diferenciar claramente entre sentimentos positivos e negativos.

**Limpeza e normalização do texto**

Cada review passa por uma função que:

* Converte para letras minúsculas
* Remove acentuação
* Remove caracteres especiais
* Elimina **stop words** (palavras comuns que não agregam significado, como “a”, “o”, “de”, “em”)

**Balanceamento de classes**

Para evitar que o modelo fique enviesado, aplicamos **oversampling** na classe minoritária, garantindo que o modelo tenha a mesma quantidade de exemplos positivos e negativos.

**Treinamento do modelo**

Utilizamos um **Pipeline** do Scikit-learn com:

* **TfidfVectorizer**: transforma o texto em vetores ponderando a frequência das palavras
* **LogisticRegression**: modelo de regressão logística para classificação binária (positivo/negativo)

---

### Análise de Reviews

**Limpeza do texto**

A review é normalizada e as stop words são removidas, garantindo consistência com os dados usados no treinamento.

**Classificação do sentimento**

Através do `.predict` do pipeline treinado, obtemos se a review é **Positiva** ou **Negativa**.
  Também calculamos a **probabilidade** da classificação, permitindo medir a confiança do modelo.

**Identificação de tópicos**

Utilizamos um **mapa de tópicos pré-definido**, com palavras-chave relacionadas a temas como: ENTREGA, QUALIDADE DO PRODUTO, ATENDIMENTO, PREÇO, PAGAMENTO, entre outros.

O texto é comparado com as palavras-chave para identificar quais tópicos estão presentes na review. Caso nenhum tópico seja identificado, o texto é classificado como `GERAL`.

**Saída da análise**

Para cada review, retornamos:

  * **Classificação**: Positivo ou Negativo
  * **Tópicos**: lista de tópicos encontrados
  * **Texto limpo**: versão normalizada usada pelo modelo
  * **Probabilidade**: confiança da classificação

Essa metodologia permite não apenas determinar o sentimento da review, mas também extrair insights sobre os principais aspectos mencionados pelos clientes, auxiliando em decisões estratégicas.

---

## Justificando as escolhas

A arquitetura e as tecnologias deste projeto foram selecionadas com foco em três pilares fundamentais: **escalabilidade**, **desacoplamento** e **automação**. O objetivo é construir um fluxo de Machine Learning (MLOps) robusto, capaz de crescer e se adaptar a novas fontes de dados com o mínimo de atrito.

### Arquitetura Orientada a Eventos com S3 e Lambda

O coração do projeto é uma arquitetura orientada a eventos, que proporciona flexibilidade e escalabilidade.

* **AWS S3 como Data Lake Central:** A escolha do S3 como repositório principal de dados (Data Lake) é estratégica. Ele é um serviço de armazenamento de objetos altamente durável, de baixo custo e praticamente infinito. A estrutura de pastas (`raw/`, `processed/`) permite uma organização clara das etapas do processo. O principal benefício é que **novas fontes de dados podem ser adicionadas simplesmente depositando arquivos no bucket `raw/`**, seja de outro sistema, um novo processo de batch ou um upload manual. Essa ação não interfere em nenhum outro componente do fluxo, pois o processamento é acionado a partir do evento de criação do arquivo.

* **AWS Lambda para Processamento Desacoplado:** O Lambda funciona como o "cérebro" reativo do nosso ETL. Ao invés de ter um servidor constantemente verificando por novos arquivos, o Lambda é **acionado automaticamente** (via S3 Events) apenas quando um novo dado chega. Isso significa que:
    * **Custo-benefício:** Pagamos apenas pelo tempo de processamento, sem custos de servidor ocioso.
    * **Escalabilidade Automática:** Se 1000 arquivos chegarem ao mesmo tempo, a AWS provisionará 1000 execuções do Lambda em paralelo, processando os dados de forma massiva sem a necessidade de gerenciamento de infraestrutura.
    * **Desacoplamento:** A função Lambda responsável pelo processamento não precisa saber se o dado veio da API ou de um upload manual. Sua única responsabilidade é ler um arquivo do S3, transformá-lo e salvá-lo em outro local. Isso torna o sistema modular e fácil de manter.

### API Gateway para Input

Para capturar dados em tempo real, como reviews enviadas por usuários, o **API Gateway** é a escolha ideal. Ele atua como uma porta de entrada gerenciada, segura e escalável, que se integra nativamente com o Lambda. Essa combinação cria um endpoint *serverless* que pode lidar com picos de tráfego sem qualquer intervenção manual.

### AWS SageMaker para o Ciclo de Vida de ML

Em vez de treinar o modelo em uma máquina local ou em uma instância EC2 simples, o **AWS SageMaker** foi escolhido por ser uma plataforma completa para o ciclo de vida de Machine Learning.

* **Ambiente Gerenciado:** O SageMaker Studio oferece um ambiente JupyterLab totalmente gerenciado, eliminando a necessidade de configurar e manter servidores.
* **Integração com o Ecossistema AWS:** Ele se conecta de forma nativa e otimizada com o S3 e o Athena, simplificando a ingestão de dados para treinamento.
* **Escalabilidade de Treinamento e Deploy:** Permite treinar modelos em instâncias computacionais poderosas e, mais importante, facilita o *deploy* do modelo treinado como um endpoint de inferência escalável, pronto para ser consumido por outras aplicações.

### Terraform para Infraestrutura como Código (IaC)

Manter a infraestrutura na nuvem de forma manual é arriscado e propenso a erros. O **Terraform** resolve esse problema ao permitir que toda a arquitetura (API Gateway, Lambdas, buckets S3, permissões) seja declarada em código. Isso garante:

* **Reprodutibilidade:** É possível recriar todo o ambiente em outra região ou conta AWS com um único comando, garantindo consistência.
* **Versionamento:** A infraestrutura é versionada junto com o código da aplicação, facilitando o rastreamento de mudanças.
* **Automação:** Modificações e atualizações na infraestrutura são feitas de forma automatizada e previsível.

Em suma, a combinação dessas tecnologias cria um pipeline de dados e ML que não é apenas funcional, mas também preparado para o futuro. A capacidade de escalar sob demanda, a flexibilidade para integrar novas fontes de dados sem redesenhar a arquitetura e a automação de ponta a ponta garantem que o sistema seja eficiente, resiliente e de fácil manutenção.