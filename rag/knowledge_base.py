from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FakeEmbeddings
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
import os
import time

class CampusKnowledgeBase:
    def __init__(self, api_key, data_dir="好人师兄"):
        self.api_key = api_key
        self.data_dir = data_dir
        self.vector_store = None
        self.qa_chain = None
        self.last_update_time = 0
        self.update_interval = 3600

        self.build_vector_store()
        self.setup_qa_chain()

    def load_documents(self):
        documents = []

        if not os.path.exists(self.data_dir):
            return documents

        for filename in os.listdir(self.data_dir):
            filepath = os.path.join(self.data_dir, filename)

            if not os.path.isfile(filepath):
                continue

            if filename.endswith(".md") or filename.endswith(".txt"):
                try:
                    loader = TextLoader(filepath, encoding='utf-8')
                    docs = loader.load()
                    # 将文件名加入元数据
                    for doc in docs:
                        doc.metadata["source"] = filename
                    documents.extend(docs)
                except Exception as e:
                    print(f"加载文件 {filename} 失败: {e}")

        return documents

    def build_vector_store(self):
        documents = self.load_documents()

        if not documents:
            return False

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len
        )

        splits = text_splitter.split_documents(documents)

        embeddings = FakeEmbeddings(size=384)
        self.vector_store = FAISS.from_documents(splits, embeddings)

        return True

    def setup_qa_chain(self):
        if not self.vector_store:
            if not self.build_vector_store():
                return False

        llm = ChatOpenAI(
            temperature=0.7,
            model="deepseek-chat",
            api_key=self.api_key,
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        )

        prompt_template = """你是广东金融学院的刘晨曦师兄，回答问题时要以老学长的口吻，靠谱、不废话。

请严格根据以下提供的上下文信息回答用户的问题。如果上下文中没有相关信息，请诚实地说"这个问题我不太清楚，建议查看学校官网或咨询辅导员"。

上下文（来自好人师兄公众号文章）：
{context}

用户问题：
{question}

回答要求：
1. 严格基于上下文内容回答，不要编造
2. 直接回答问题核心
3. 保持亲切、实用的语气
"""

        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "question"]
        )

        retriever = self.vector_store.as_retriever(k=3)

        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)

        self.qa_chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )

        return True

    def manual_update(self):
        try:
            self.build_vector_store()
            self.setup_qa_chain()
            self.last_update_time = time.time()
            doc_count = len(self.load_documents())
            return True, f"知识库更新成功！已加载 {doc_count} 篇文章"
        except Exception as e:
            return False, f"更新失败：{str(e)}"

    def query(self, question):
        if not self.qa_chain:
            if not self.setup_qa_chain():
                return "知识库尚未加载，请将文章放入好人师兄文件夹。"

        try:
            answer = self.qa_chain.invoke(question)
            return answer
        except Exception as e:
            return f"检索失败：{str(e)}"
