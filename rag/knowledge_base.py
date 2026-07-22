from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FakeEmbeddings
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
import os

class CampusKnowledgeBase:
    def __init__(self, api_key, data_dir="data"):
        self.api_key = api_key
        self.data_dir = data_dir
        self.vector_store = None
        self.qa_chain = None
        
        load_sample_data(data_dir)
    
    def load_documents(self):
        documents = []
        
        for filename in os.listdir(self.data_dir):
            filepath = os.path.join(self.data_dir, filename)
            
            if filename.endswith(".txt"):
                loader = TextLoader(filepath, encoding='utf-8')
                docs = loader.load()
                documents.extend(docs)
            
            elif filename.endswith(".pdf"):
                try:
                    loader = PyPDFLoader(filepath)
                    docs = loader.load()
                    documents.extend(docs)
                except:
                    continue
        
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
        
        prompt_template = """你是广东金融学院的万事屋师兄，回答问题时要以老学长的口吻，靠谱、不废话，并且给出实用的避坑建议。

请根据以下提供的上下文信息回答用户的问题：

上下文：
{context}

用户问题：
{question}

请用广东金融学院学生熟悉的语言风格回答，确保信息准确，不要编造。如果上下文没有相关信息，请诚实地说"这个问题我不太清楚"。

回答要求：
1. 直接回答问题核心
2. 给出具体建议或路线指引
3. 添加一个避坑提醒（如果适用）
4. 保持亲切、实用的语气
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
    
    def query(self, question):
        if not self.qa_chain:
            if not self.setup_qa_chain():
                return "知识库尚未加载，请先放入文档到data目录。"
        
        try:
            answer = self.qa_chain.invoke(question)
            return answer
        except Exception as e:
            return f"检索失败：{str(e)}"

def load_sample_data(data_dir="data"):
    os.makedirs(data_dir, exist_ok=True)
    
    sample_path = os.path.join(data_dir, "sample_guide.txt")
    if os.path.exists(sample_path):
        return
    
    sample_content = """# 广东金融学院龙洞校区指南

## 校园路线

### 图书馆到6教路线
从图书馆正门出来，沿着主干道向南走，经过行政楼后右转，直行200米即可到达6教。
避坑提醒：6教没有电梯，上课高峰期楼梯比较拥挤，建议提前10分钟到达。

### 饭堂位置
龙洞校区有两个饭堂：第一饭堂位于教学楼群东侧，第二饭堂位于学生宿舍区附近。
建议：第一饭堂性价比高，第二饭堂环境较好但价格稍贵。

### 快递点位置
菜鸟驿站位于西门附近，顺丰快递点在宿舍区B栋楼下。

## 生活服务

### 空调报修
报修电话：020-87053888
报修时间：工作日 8:30-17:30
注意：报修后一般24小时内会有人上门维修，建议提前预约。

### 校园卡充值
充值地点：第一饭堂旁边的校园卡服务中心
充值时间：周一至周五 8:00-12:00, 14:00-17:00
也可以通过"广金校园"APP在线充值。

### 校医院
位置：图书馆北侧
就诊时间：8:00-12:00, 14:30-17:30
注意：校医院药品较齐全，但大病建议去市区医院。

## 教学楼分布

### 1-3教
主要用于公共课教学，位于校园西侧。

### 4-6教
主要用于专业课教学，位于校园东侧。

### 实验楼
位于校园北侧，计算机学院和金融工程学院在此上课。

## 宿舍区

### A栋-C栋
大一新生主要居住在此区域。

### D栋-F栋
大二及以上学生居住区域。

## 注意事项

1. 校园内禁止骑电动车，只能步行或骑自行车。
2. 图书馆占座现象严重，建议早起或使用预约系统。
3. 饭堂高峰期（11:30-12:30）人很多，建议错峰用餐。
4. 宿舍门禁时间：周日至周四 23:30，周五周六 00:00。
"""
    
    with open(sample_path, "w", encoding="utf-8") as f:
        f.write(sample_content)