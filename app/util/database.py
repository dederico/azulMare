import os
import sqlite3
from logger import logger
from app.models import Call, User, Config

class LocalStorage:
    def __init__(self, dbName='my-db'):
        self.filename = dbName
        logger.debug("Preparing local storage")
        if not os.path.exists(self.filename):
            self.__create_table(Call)
            self.__create_table(User)
            self.__create_table(Config)

            logger.info("New Local DB has been created Successfully")
        logger.debug("Local storage has been initialized")

    def __create_table(self, model_cls):
        try:
            conn = sqlite3.connect(self.filename)
            cursor = conn.cursor()

            table_name = f"{model_cls.__name__.lower()}s"
            logger.debug("Creating table " + table_name)
            fields = ', '.join([f"{field} {data_type}" for field, data_type in model_cls.__annotations__.items()])

            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {fields}
                )
            ''')

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(e)
            return False
    
    def GetAll(model):
        try:
            conn = sqlite3.connect(self.filename)
            cursor = conn.cursor()

            cursor.execute(f"SELECT * FROM {type(model).__name__.lower()}s")

            records = []
            for row in cursor.fetchall():
                record = model(**dict(row))
                records.append(record)

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
            fields = ', '.join(data.__dict__.keys())
            placeholders = ', '.join(['?' for _ in range(len(data.__dict__))])

            values = [getattr(data, field) for field in data.__dict__.keys()]
            cursor.execute(f'''
                UPDATE {table_name}
                SET {', '.join([f"{field} = ?" for field in fields.split(",")])}
                WHERE id = ?
            ''', values + [data.id])


            conn.commit()

            conn.close()
            logger.info("Existing record updated successfully in Local Storage")
            return data
        except Exception as e:
            logger.error(e)
            return False