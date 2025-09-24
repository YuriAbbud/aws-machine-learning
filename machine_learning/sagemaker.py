# É necessário configurar os acessos no Lake Formation para a role do SageMaker

import pandas as pd
import awswrangler as wr
import re
import unicodedata
import nltk
from nltk.corpus import stopwords
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.linear_model import LogisticRegression
from sklearn.utils import resample

database_name = 'machine_learning_database'
table_name = 'processed_review'

try:
    stop_words = stopwords.words('portuguese')
except LookupError:
    nltk.download('stopwords')
    stop_words = stopwords.words('portuguese')

def remover_acentos(texto):
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )

def limpar_texto(texto):
    texto = str(texto).lower()
    texto = remover_acentos(texto)

    texto = re.sub(r'[^a-z\s_]', ' ', texto)

    palavras = texto.split()
    palavras_sem_stopwords = [p for p in palavras if p not in stop_words]

    return " ".join(palavras_sem_stopwords)

try:
    df = wr.athena.read_sql_query(
        sql=f"SELECT review_score, review_comment_message FROM {table_name} WHERE review_comment_message <> 'review_comment_message' AND review_score <> 3",
        database=database_name,
        ctas_approach=False
    )
    print(f"Dados carregados com sucesso: {len(df)} linhas.")

    df.dropna(subset=['review_comment_message'], inplace=True)
    df = df[df['review_comment_message'].str.strip().astype(bool)]
    df['review_score'] = pd.to_numeric(df['review_score'], errors='coerce')
    df.dropna(subset=['review_score'], inplace=True)
    df['review_score'] = df['review_score'].astype(int)

    df['classificacao'] = df['review_score'].apply(lambda score: 1 if score > 3 else 0)

    df_model = df[['review_comment_message', 'classificacao']].copy()
    df_model['texto_limpo'] = df_model['review_comment_message'].apply(limpar_texto)

    print("\nContagem de classes antes do balanceamento:")
    print(df_model['classificacao'].value_counts().rename({0: 'Negativo', 1: 'Positivo'}))

    df_neg = df_model[df_model['classificacao'] == 0]
    df_pos = df_model[df_model['classificacao'] == 1]

    if len(df_neg) < len(df_pos):
        df_neg = resample(df_neg, replace=True, n_samples=len(df_pos), random_state=42)
    elif len(df_pos) < len(df_neg):
        df_pos = resample(df_pos, replace=True, n_samples=len(df_neg), random_state=42)

    df_model = pd.concat([df_pos, df_neg])


    print("\nContagem de classes após balanceamento:")
    print(df_model['classificacao'].value_counts().rename({0: 'Negativo', 1: 'Positivo'}))

    X = df_model['texto_limpo']
    y = df_model['classificacao']
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(ngram_range=(1, 2))),
        ('clf', LogisticRegression(solver='liblinear', random_state=42))
    ])
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    print(f"\nPrecição: {accuracy:.2%}")
    print("\nRelatório de Classificação:")
    print(classification_report(y_test, y_pred, target_names=["Negativo", "Positivo"]))

    print("Matriz de Confusão:")
    print(confusion_matrix(y_test, y_pred))

    mapa_topicos = {
        "ENTREGA": [
            "entrega", "prazo", "chegou", "rapido", "rapida", "demorou",
            "atraso", "embalagem", "correios", "frete", "transportadora",
            "rastreio", "logistica"
        ],

        "QUALIDADE DO PRODUTO": [
            "qualidade", "produto", "material", "perfeito", "excelente",
            "ruim", "quebrado", "defeito", "funciona", "funcionou",
            "gostei", "bonito", "horrivel", "durabilidade", "acabamento",
            "resistente", "fragil", "original", "falsificado"
        ],

        "ATENDIMENTO": [
            "atendimento", "vendedor", "loja", "resposta", "contato",
            "suporte", "atencao", "educado", "mal educado", "gentil",
            "demorado", "prestativo", "descaso"
        ],

        "PRECO": [
            "preco", "caro", "barato", "custo", "valor", "compra",
            "carissimo", "promocao", "oferta", "desconto", "custo beneficio"
        ],

        "PAGAMENTO": [
            "pagamento", "boleto", "cartao", "credito", "debito", "pix",
            "parcelamento", "juros", "cobranca", "fatura"
        ],

        "PLATAFORMA / SITE": [
            "site", "aplicativo", "app", "plataforma", "navegacao",
            "facil", "dificil", "erro", "bug", "trava", "compra online",
            "checkout"
        ],

        "EXPERIÊNCIA GERAL": [
            "satisfeito", "insatisfeito", "recomendo", "nao recomendo",
            "horrivel", "otimo", "pessimo", "excelente", "amei", "odiei",
            "voltar", "comprarei", "experiencia", "arrependo"
        ],

        "SERVIÇO": [
            "servico", "instalacao", "manutencao", "garantia", "troca",
            "devolucao", "suporte tecnico", "conserto", "assistencia"
        ],

        "USABILIDADE / FUNCIONALIDADE": [
            "facil", "complicado", "funcional", "rapido", "intuitivo",
            "dificil", "simples", "pratico", "bugado", "lento"
        ],

        "ESTÉTICA / DESIGN": [
            "bonito", "feio", "design", "moderno", "antigo", "cor",
            "tamanho", "forma", "aparencia", "estilo"
        ]
    }

    def identificar_topicos(texto_original):
        texto_limpo = limpar_texto(texto_original)
        topicos_encontrados = set()
        for topico, palavras_chave in mapa_topicos.items():
            for palavra in palavras_chave:
                if palavra in texto_limpo:
                    topicos_encontrados.add(topico)
        return list(topicos_encontrados) if topicos_encontrados else ['GERAL']

    def analisar_review_com_ml(texto_original):
        texto_limpo_para_previsao = limpar_texto(texto_original)
        previsao_classificacao = pipeline.predict([texto_limpo_para_previsao])[0]
        probabilidade = pipeline.predict_proba([texto_limpo_para_previsao])[0][previsao_classificacao]
        mapa_classificacao = {0: 'Negativo', 1: 'Positivo'}
        classificacao_final = mapa_classificacao[previsao_classificacao]
        topicos_da_review = identificar_topicos(texto_original)
        return classificacao_final, topicos_da_review, texto_limpo_para_previsao, probabilidade

    reviews_para_teste = [
        "Simplesmente incrível! Superou todas as minhas expectativas.",
        "Material de excelente qualidade e acabamento impecável.",
        "Chegou muito antes do prazo e perfeitamente embalado. Recomendo!",
        "A entrega atrasou demais e não recebi nenhuma satisfação.",
        "Produto de péssima qualidade, quebrou no primeiro dia de uso.",
        "Infelizmente, o item não funciona como deveria.",
        "A cor do produto veio totalmente diferente da foto no site.",
        "O design é muito bonito, porém o material parece frágil.",
        "Gostei do produto, mas a embalagem veio danificada.",
        "A montagem foi um pouco difícil, mas o resultado final ficou bom."
    ]

    print("\n--- Testando com reviews ---")
    for review in reviews_para_teste:
        classificacao, topicos, texto_limpo, probabilidade = analisar_review_com_ml(review)
        print("-" * 50)
        print(f"Original: {review}")
        print(f"Probabilidade: {probabilidade:.2%}")
        print(f"Classificação: {classificacao}")
        print(f"Tópicos: {topicos}")

except Exception as e:
    print(f"\nOcorreu um erro: {e}")
