import os
import sqlite3
from .logger import logger
from app.models.Call import Call
from app.models.Config import Config
from app.models.User import User
from app.models.Notification import Notification

class LocalStorage:
    def __init__(self, dbName='my-db.db'):
        tables = [Call, User, Config, Notification]
        self.filename = dbName
        logger.debug("Preparing local storage")

        for table in tables:
            self.__create_table(table)

        logger.debug("Local storage has been initialized")

    def __create_table(self, model_cls):
        try:
            conn = sqlite3.connect(self.filename)
            cursor = conn.cursor()

            table_name = f"{model_cls.__name__.lower()}s"
            logger.debug("Creating/Checking table " + table_name)
            fields = ', '.join([f"{field} {data_type.__name__}" for field, data_type in model_cls.__annotations__.items()])
            query = f'''
                CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {fields}
                )
            '''

            cursor.execute(query)

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(e)
            return False
    
    def GetByPK(self, model, id, json=False):
        try:
            conn = sqlite3.connect(self.filename)
            cursor = conn.cursor()

            cursor.execute(f"SELECT * FROM {model.__name__.lower()}s where id = {id}")
            column_names = [column[0] for column in cursor.description]

            record = cursor.fetchone()
            record = model(**dict(zip(column_names, record))) if not json else dict(zip(column_names, record))

            conn.close()
            return record
        except Exception as e:
            logger.error(e)
            return None

    def GetAll(self, model, rawQuery=False, json=False):
        try:
            conn = sqlite3.connect(self.filename)
            cursor = conn.cursor()

            cursor.execute(rawQuery or f"SELECT * FROM {model.__name__.lower()}s")
            column_names = [column[0] for column in cursor.description]

            records = []
            for row in cursor.fetchall():
                if not json:
                    records.append(model(**dict(zip(column_names, row))))
                else:
                    records.append(dict(zip(column_names, row)))

            conn.close()
            return records
        except Exception as e:
            logger.error(e)
            return []

    def Insert(self, data):
        try:
            logger.debug("Trying to insert new model entry in local storage")
            conn = sqlite3.connect(self.filename)
            cursor = conn.cursor()

            table_name = f"{type(data).__name__.lower()}s"
            fields = ', '.join(data.__dict__.keys())
            placeholders = ', '.join(['?' for _ in range(len(data.__dict__))])

            values = [getattr(data, field) for field in data.__dict__.keys()]
            cursor.execute(f'''
                INSERT INTO {table_name} ({fields})
                VALUES ({placeholders})
            ''', values)

            conn.commit()
            setattr(data, 'id', cursor.lastrowid)

            conn.close()
            logger.info("New record added successfully in Local Storage")
            return data
        except Exception as e:
            logger.error(e)
            return False
    
    def Update(self, data):
        try:
            if not hasattr(data, 'id'):
                logger.warning("Unique ID not found in data instance skipping update")
                return False

            logger.debug("Trying to Update existing model entry in local storage")
            conn = sqlite3.connect(self.filename)
            cursor = conn.cursor()

            table_name = f"{type(data).__name__.lower()}s"
            placeholders = ', '.join(['?' for _ in range(len(data.__dict__))])

            values = [getattr(data, field) for field in data.__dict__.keys()]
            cursor.execute(f'''
                UPDATE {table_name}
                SET {', '.join([f"{field} = ?" for field in data.__dict__.keys()])}
                WHERE id = ?
            ''', values + [data.id])


            conn.commit()

            conn.close()
            logger.info("Existing record updated successfully in Local Storage")
            return data
        except Exception as e:
            logger.error(e)
            return False