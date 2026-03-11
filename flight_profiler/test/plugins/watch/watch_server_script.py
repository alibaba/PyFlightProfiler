import sys
import time


class A:
    def hello(self):
        try:
            return exp_func()
        except:
            return test_func("hello")

    @classmethod
    def cls_method(cls):
        return test_func("hello")

    def nested_method(self):
        def nested_func_inner():
            return test_func("nested_method")
        return nested_func_inner()

def kwonly_func(x, y, *, c=1):
    print("kwonly_func called")
    
    
def test_func(name):
    print("hello func")
    return name + " " + "watch_plugin"


def exp_func():
    return 1 / 0


print("plugin unit test script started\n")
sys.stdout.flush()

idx = 1
while True:
    A().hello()
    A().nested_method()
    A.cls_method()
    kwonly_func("kwonly_func_called", 2)
    time.sleep(1)
    idx += 1
