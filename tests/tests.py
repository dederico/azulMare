import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from app.models.Config import Config
from app.util.database import LocalStorage

ls = LocalStorage()

class TestConfigModel(unittest.TestCase):
    def test_model_init(self):
        c = Config(name="test_key", value='test_value')
        self.assertEqual(c.name, "test_key")
        
    def test_model_is_not_dirty(self):
        c = Config(name="test_key", value='test_value')
        self.assertFalse(c.isDirty)
        
    def test_model_is_dirty(self):
        c = Config(name="test_key", value='test_value')
        c.value ='new_test_value'
        self.assertTrue(c.isDirty)

class TestLocalStorage(unittest.TestCase):
    def test_add_config(self):
        r = ls.Insert(Config(name="test_key", value='test_value'))
        self.assertEqual(r and hasattr(r, 'id') and r.id > 0, True)
        
    def test_find_config(self):
        r = ls.Search(Config(name="test_key"), True)
        self.assertEqual(r.value, 'test_value')
        
    def test_update_config(self):
        r = ls.Search(Config(name="test_key"), True)
        r.value = 'new_test_value'
        r = ls.Update(r)
        self.assertEqual(r.value, 'new_test_value')
    
    def test_remove_config(self):
        r = ls.Search(Config(name="test_key"), True)
        self.assertEqual(ls.Remove(r), True)

def suite():
    suite = unittest.TestSuite()
    suite.addTest(TestLocalStorage('test_add_config'))
    suite.addTest(TestLocalStorage('test_find_config'))
    suite.addTest(TestLocalStorage('test_update_config'))
    suite.addTest(TestLocalStorage('test_remove_config'))

    suite.addTest(TestConfigModel('test_model_init'))
    suite.addTest(TestConfigModel('test_model_is_not_dirty'))
    suite.addTest(TestConfigModel('test_model_is_dirty'))


    return suite

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())
