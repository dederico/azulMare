import os
import psycopg2
from psycopg2 import Binary
from psycopg2 import sql
from .logger import logger
from app.models.Call import Call
from app.models.Config import Config
from app.models.User import User
from app.models.File import File
from app.models.Message import Message
from app.models.OutgoingCampaign import OutgoingCampaign
from app.models.OutgoingRecipient import OutgoingRecipient
from dotenv import load_dotenv
from app.models.Notification import Notification
# from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

load_dotenv()

# class VectorBase:
#     def __init__(self, db):
#         #self.pc = Pinecone(environment=db)
#         self.model = SentenceTransformer("all-MiniLM-L6-v2")
#         if db != None:
#             self.db = db
#             self.index = self.pc.Index(db)

#     def Query(self, q, top_k=2):
#         input_em = self.model.encode(q).tolist()
#         result = self.index.query(vector=input_em, top_k=top_k, includeMetadata=True)
#         if len(result['matches']) >= top_k:
#             return result['matches'][0]['metadata']['text']+"\n"+result['matches'][1]['metadata']['text']
#         return None

class LocalStorage:
    def __init__(self):
        self.dbName = os.environ.get("DATABASE")
        self.user = os.environ.get("DB_USERNAME")
        self.password = os.environ.get("DB_PASSWORD")
        self.host = os.environ.get("DB_HOST")
        self.port = os.environ.get("DB_PORT")

        self.connection_url = (
            f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.dbName}?sslmode=require"
        )

        logger.debug(f"Local storage has been initialized with URL: {self.connection_url}")

    def migrate(self):
        tables = [Call, User, Config, Notification, File, Message, OutgoingCampaign, OutgoingRecipient]
        for table in tables:
            self.__verify_schema(table)

    def __verify_schema(self, model_cls):
        try:
            conn = psycopg2.connect(dbname=self.dbName, user=self.user, password=self.password, host=self.host, port=self.port)
            cursor = conn.cursor()

            table_name = f"{model_cls.__name__.lower()}s"
            logger.debug("Creating/Checking/Updating table " + table_name)

            cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}';")
            existing_columns = [row[0] for row in cursor.fetchall()]

            model_fields = model_cls.__annotations__

            fields_to_add = []
            fields_to_remove = []

            for field, data_type in model_fields.items():
                if field not in existing_columns:
                    fields_to_add.append(f"ADD COLUMN \"{field}\" {self.get_pg_data_type(data_type)}")

            for existing_column in existing_columns:
                if existing_column != "id" and existing_column not in model_fields:
                    fields_to_remove.append(f"DROP COLUMN \"{existing_column}\"")

            cursor.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}');")
            table_exists = cursor.fetchone()[0]

            if not table_exists:
                logger.debug(f"Table {table_name} does not exist. Creating table.")
                fields = ', '.join([f"\"{field}\" {self.get_pg_data_type(data_type)}" for field, data_type in model_fields.items()])
                create_query = sql.SQL('''
                    CREATE TABLE {table} (
                        "id" SERIAL PRIMARY KEY,
                        {fields}
                    )
                '''.strip()).format(
                    table=sql.Identifier(table_name),
                    fields=sql.SQL(fields)
                )
                cursor.execute(create_query)
            elif fields_to_add or fields_to_remove:
                logger.debug(f"Updating table {table_name}. Adding: {fields_to_add}, Removing: {fields_to_remove}")
                alter_query = f"ALTER TABLE {table_name} " + ', '.join(fields_to_add + fields_to_remove)
                cursor.execute(alter_query)

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(e)
            return False

    # Añadir este método a la clase LocalStorage
    def delete_messages_by_number(self, number):
        try:
            conn = psycopg2.connect(dbname=self.dbName, user=self.user, password=self.password, host=self.host, port=self.port)
            cursor = conn.cursor()
            
            # Asegurarse que number sea un string o un valor que psycopg2 pueda adaptar
            if isinstance(number, str):
                # SQL directo para eliminar mensajes por número
                cursor.execute("DELETE FROM messages WHERE number = %s", [number])
            else:
                # Si no es string, convertirlo
                cursor.execute("DELETE FROM messages WHERE number = %s", [str(number)])
                
            count = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            return count
        except Exception as e:
            logger.error(f"Error eliminando mensajes por número: {str(e)}")
            return 0

    @staticmethod
    def get_pg_data_type(python_type):
        type_mappings = {
            int: 'INTEGER',
            str: 'TEXT',
            float: 'REAL',
            bool: 'BOOLEAN',
            bytes: 'BYTEA'
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

    def Search(self, model, single=False, json=False, limit=0, order='desc', order_col='id'):
        try:
            conn = psycopg2.connect(dbname=self.dbName, user=self.user, password=self.password, host=self.host, port=self.port)
            cursor = conn.cursor()

            attributes = {attr: getattr(model, attr) for attr in model.__dict__.keys() if not attr.startswith("_")}

            query_parts = [
                "SELECT * FROM {table}",
                "WHERE " + " AND ".join([f"\"{sql.Identifier(attr).string}\" = %s" for attr in attributes])
            ]

            if order.lower() in ['asc', 'desc']:
                query_parts.append(f"ORDER BY {order_col} {order.upper()}")

            if limit > 0:
                query_parts.append(f"LIMIT {limit}")

            query = sql.SQL(" ".join(query_parts)).format(
                table=sql.Identifier(model.__class__.__name__.lower() + 's')
            )

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

    def GetAll(self, model, rawQuery=False, json=False, cols=[]):
        try:
            conn = psycopg2.connect(dbname=self.dbName, user=self.user, password=self.password, host=self.host, port=self.port)
            cursor = conn.cursor()

            cols = sql.SQL("*") if len(cols) == 0 else sql.SQL(", ").join(map(sql.Identifier, cols))

            cursor.execute(rawQuery or sql.SQL("SELECT {cols} FROM {table}").format(
                table=sql.Identifier(model.__name__.lower() + 's'),
                cols=cols
            ))
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

            if isinstance(data, list):
                if len(data) == 0:
                    return False

                table_name = f"{type(data[0]).__name__.lower()}s"  # Use the type of the first element in the list
                all_payloads = [
                    {field: value for field, value in entry.__dict__.items() if field != '_dirty_attributes'}
                    for entry in data
                ]
            
                fields = ', '.join([f'"{sql.Identifier(field).string}"' for field in all_payloads[0].keys()])
                placeholders = ', '.join(['%s' for _ in all_payloads[0].keys()])

                query = sql.SQL('''
                    INSERT INTO {table} ({fields})
                    VALUES ({placeholders})
                ''').format(
                    table=sql.Identifier(table_name),
                    fields=sql.SQL(fields),
                    placeholders=sql.SQL(placeholders)
                )

                values = [
                    [Binary(v) if isinstance(v, bytes) else v for v in list(entry.values())]
                    for entry in all_payloads
                ]

                cursor.executemany(query, values)
                conn.commit()
                conn.close()
                logger.info("Bulk records added successfully in Local Storage")
                return True
            else:
                table_name = f"{type(data).__name__.lower()}s"
                payload = {field: value for field, value in data.__dict__.items() if field != '_dirty_attributes'}

                fields = ', '.join([f'"{sql.Identifier(field).string}"' for field in payload.keys()])
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

                values = [Binary(v) if isinstance(v, bytes) else v for v in list(payload.values())]
                cursor.execute(query, values)
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
            fields = ', '.join([f"\"{sql.Identifier(field).string}\" = %s" for field in payload.keys() ])

            query = sql.SQL('''
                UPDATE {table}
                SET {fields}
                WHERE id = %s
            ''').format(
                table=sql.Identifier(table_name),
                fields=sql.SQL(fields)
            )
            values = [ Binary(v) if type(v) == bytes else v for v in list(payload.values())]
            cursor.execute(query, values + [data.id])

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
            fields = ' AND '.join([f"\"{sql.Identifier(field).string}\" = %s" for field in payload.keys()])
    
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
