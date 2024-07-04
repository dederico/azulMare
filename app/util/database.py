import os
import psycopg2
from psycopg2 import sql
from .logger import logger
from app.models.Call import Call
from app.models.Config import Config
from app.models.User import User
from app.models.Notification import Notification

class LocalStorage:
    def __init__(self, dbName='callgpt', user='postgres', password='', host='localhost', port='5432'):
        self.dbName = os.environ.get("DATABASE") or dbName
        self.user = os.environ.get("DB_USERNAME") or user
        self.password = os.environ.get("DB_PASSWORD") or password
        self.host = os.environ.get("DB_HOST") or host
        self.port = os.environ.get("DB_PORT") or port
        tables = [Call, User, Config, Notification]
        logger.debug("Preparing local storage")

        for table in tables:
            self.__create_table(table)

        logger.debug("Local storage has been initialized")

    def __create_table(self, model_cls):
        try:
            conn = psycopg2.connect(dbname=self.dbName, user=self.user, password=self.password, host=self.host, port=self.port)
            cursor = conn.cursor()

            table_name = f"{model_cls.__name__.lower()}s"
            logger.debug("Creating/Checking table " + table_name)
            fields = ', '.join([f"\"{sql.Identifier(field).string}\" {self.get_pg_data_type(data_type)}" for field, data_type in model_cls.__annotations__.items()])
            query = sql.SQL('''
                CREATE TABLE IF NOT EXISTS {table} (
                    "id" SERIAL PRIMARY KEY,
                    {fields}
                )
            '''.strip()).format(
                table=sql.Identifier(table_name),
                fields=sql.SQL(fields)
            )

            cursor.execute(query)

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(e)
            return False

    @staticmethod
    def get_pg_data_type(python_type):
        type_mappings = {
            int: 'INTEGER',
            str: 'TEXT',
            float: 'REAL',
            bool: 'BOOLEAN'
        }
        return type_mappings.get(python_type, 'TEXT')

    def GetByPK(self, model, id, json=False):
        try:
            conn = psycopg2.connect(dbname=self.dbName, user=self.user, password=self.password, host=self.host, port=self.port)
            cursor = conn.cursor()

            cursor.execute(sql.SQL("SELECT * FROM {table} WHERE id = %s").format(
                table=sql.Identifier(model.__name__.lower() + 's')), [id])
            column_names = [desc[0] for desc in cursor.description]

            record = cursor.fetchone()
            record = model(**dict(zip(column_names, record))) if not json else dict(zip(column_names, record))

            conn.close()
            return record
        except Exception as e:
            logger.error(e)
            return None

    def Search(self, model, single=False, json=False):
        try:
            conn = psycopg2.connect(dbname=self.dbName, user=self.user, password=self.password, host=self.host, port=self.port)
            cursor = conn.cursor()

            attributes = {attr: getattr(model, attr) for attr in model.__dict__.keys() if not attr.startswith("_")}
            query = sql.SQL("SELECT * FROM {table} WHERE " + " AND ".join([f"{sql.Identifier(attr).string} = %s" for attr in attributes])).format(
                table=sql.Identifier(model.__class__.__name__.lower() + 's'))
            cursor.execute(query, list(attributes.values()))

            column_names = [desc[0] for desc in cursor.description]

            records = cursor.fetchall() if not single else cursor.fetchone()
            results = []
            if records:
                if not single:
                    for record in records:
                        result = model.__class__(**dict(zip(column_names, record))) if not json else dict(zip(column_names, record))
                        results.append(result)
                else:
                    results = model.__class__(**dict(zip(column_names, records))) if not json else dict(zip(column_names, records))

            conn.close()
            return results if records else None
        except Exception as e:
            logger.error(e)
            return None

    def GetAll(self, model, rawQuery=False, json=False):
        try:
            conn = psycopg2.connect(dbname=self.dbName, user=self.user, password=self.password, host=self.host, port=self.port)
            cursor = conn.cursor()

            cursor.execute(rawQuery or sql.SQL("SELECT * FROM {table}").format(
                table=sql.Identifier(model.__name__.lower() + 's')))
            column_names = [desc[0] for desc in cursor.description]

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
            conn = psycopg2.connect(dbname=self.dbName, user=self.user, password=self.password, host=self.host, port=self.port)
            cursor = conn.cursor()

            table_name = f"{type(data).__name__.lower()}s"
            payload = { field: value for field, value in data.__dict__.items() if field != '_dirty_attributes' }

            fields = ', '.join([sql.Identifier(field).string for field in payload.keys() ])
            placeholders = ', '.join(['%s' for _ in range(len(payload))])
            
            query = sql.SQL('''
                INSERT INTO {table} ({fields})
                VALUES ({placeholders})
                RETURNING id
            ''').format(
                table=sql.Identifier(table_name),
                fields=sql.SQL(fields),
                placeholders=sql.SQL(placeholders)
            )
            cursor.execute(query, list(payload.values()))
            data.id = cursor.fetchone()[0]

            conn.commit()
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
            conn = psycopg2.connect(dbname=self.dbName, user=self.user, password=self.password, host=self.host, port=self.port)
            cursor = conn.cursor()

            table_name = f"{type(data).__name__.lower()}s"
            payload = { field: value for field, value in data.__dict__.items() if field != '_dirty_attributes' }
            fields = ', '.join([f"{sql.Identifier(field).string} = %s" for field in payload.keys() ])

            query = sql.SQL('''
                UPDATE {table}
                SET {fields}
                WHERE id = %s
            ''').format(
                table=sql.Identifier(table_name),
                fields=sql.SQL(fields)
            )
            cursor.execute(query, list(payload.values()) + [data.id])

            conn.commit()
            conn.close()
            logger.info("Existing record updated successfully in Local Storage")
            return data
        except Exception as e:
            logger.error(e)
            return False
    
    def Remove(self, data):
        try:
            if data and not hasattr(data, 'id'):
                logger.warning("Unique ID not found in data instance, skipping removal")
                return False
    
            logger.debug("Trying to remove existing model entry in local storage")
            conn = psycopg2.connect(dbname=self.dbName, user=self.user, password=self.password, host=self.host, port=self.port)
            cursor = conn.cursor()
    
            table_name = f"{type(data).__name__.lower()}s"
            payload = {field: value for field, value in data.__dict__.items() if field != '_dirty_attributes' and field != 'id'}
            fields = ' AND '.join([f"{sql.Identifier(field).string} = %s" for field in payload.keys()])
    
            query = sql.SQL('''
                DELETE FROM {table}
                WHERE id = %s AND {fields}
            ''').format(
                table=sql.Identifier(table_name),
                fields=sql.SQL(fields)
            )
    
            cursor.execute(query, [data.id] + list(payload.values()))
    
            conn.commit()
            logger.info("Existing record removed successfully in local storage")
            return True
        except Exception as e:
            logger.error(e)
            return False
        finally:
            if conn:
                conn.close()
