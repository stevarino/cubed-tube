
from dataclasses import dataclass
from typing import Optional, Union, List
import unittest

from cubed_tube.lib.schema import Schema


@dataclass
class Foo(Schema):
    foo: str

@dataclass
class Bar(Schema):
    bar: str
    foo_var: Optional[Foo]


class TestDataClass(unittest.TestCase):
    def test_dataclass(self):
        data = {'foo': '1'}
        foo = Foo.from_dict(data)
        self.assertEqual(foo.foo, '1')
        self.assertEqual(foo.as_dict(), data)

    def test_dataclass_failure(self):
        with self.assertRaises(ValueError):
            Foo.from_dict({'bar': '1'})
        
        with self.assertRaises(ValueError):
            Foo.from_dict({'foo': '1', 'bar': '2'})
        
    def test_optional(self):
        data = {'bar': '3'}
        bar = Bar.from_dict(data)
        self.assertIsNone(bar.foo_var)
        
        self.assertEqual(bar.as_dict(allow_none=False), data)
        
        data.update(foo_var=None)
        self.assertEqual(bar.as_dict(allow_none=True), data)

        data = {'bar': '3', 'foo_var': {'foo': 4}}
        bar = Bar.from_dict(data)
        self.assertEqual(bar.foo_var.foo, 4)
        self.assertEqual(bar.as_dict(), data)

    def test_list(self):
        @dataclass
        class Foos(Schema):
            foos: List[Foo]

        data = {'foos': [{'foo': 'a'}, {'foo': 'b'}]}
        foos = Foos.from_dict(data)
        self.assertEqual(' '.join(v.foo for v in foos.foos), 'a b')
        self.assertEqual(foos.as_dict(), data)

        self.assertEqual(Foos.from_dict({'foos': []}).foos, [])

    def test_opt_list(self):        
        @dataclass
        class OptFoos(Schema):
            foos: Optional[List[Foo]]

        data = {'foos': [{'foo': 'a'}, {'foo': 'b'}]}
        foos = OptFoos.from_dict(data)
        self.assertEqual(' '.join(v.foo for v in foos.foos), 'a b')


    def test_list_opts(self):        
        @dataclass
        class OptFoos(Schema):
            foos: Optional[List[Optional[Foo]]]

        data = {'foos': [{'foo': 'a'}, {'foo': 'b'}, None]}
        foos = OptFoos.from_dict(data)
        self.assertEqual(' '.join(v.foo for v in foos.foos if v), 'a b')

    def test_union(self):
        @dataclass
        class FooOrBar(Schema):
            items: List[Union[Foo, Bar, None]]
        
        data = {'items': [
            {'foo': 'a'},
            {'foo': 'b'},
            {'bar': 'c'},
            None
        ]}

        obj = FooOrBar.from_dict(data)
        self.assertEqual(obj.as_dict(), data)
        self.assertEqual(
            ' '.join([obj.items[0].foo, obj.items[1].foo, obj.items[2].bar]), 
            'a b c')

        @dataclass
        class MaybeFooOrBar(Schema):
            items: Optional[List[Union[Foo, Bar, None]]]
        
        obj = FooOrBar.from_dict(data)
        self.assertEqual(obj.as_dict(), data)
        self.assertEqual(
            ' '.join([obj.items[0].foo, obj.items[1].foo, obj.items[2].bar]), 
            'a b c')

if __name__ == '__main__':
    unittest.main()