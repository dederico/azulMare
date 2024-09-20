import os
import fitz
from io import BytesIO
from docx import Document
from app.models.File import File
from app.util.database import LocalStorage

class FileParser:
    def __init__(self, name):
        ls = LocalStorage()
        file = ls.Search(File(name=name), True)
        self.extension = os.path.splitext(name)[1].lower()
        self.data = file.data

    def Parse(self):
        mapping = {
            ".docx": self.__docx,
            ".doc": self.__docx,
            ".pdf": self.__pdf
        }

        try:
            if self.extension in mapping:
                return mapping[self.extension](self.data)
            return False
        except Exception as e:
            print(e)
            return False

    def __docx(self, doc):
        doc = Document(BytesIO(doc))

        full_text = []
        for paragraph in doc.paragraphs:
            full_text.append(paragraph.text)

        return '\n'.join(full_text)
    
    def __pdf(self, pdf_bytes):
        pdf_document = fitz.open(stream=BytesIO(pdf_bytes), filetype="pdf")
    
        pdf_text = ""

        for page_num in range(pdf_document.page_count):
            page = pdf_document.load_page(page_num)
            pdf_text += page.get_text("text")

        pdf_document.close()

        return pdf_text
