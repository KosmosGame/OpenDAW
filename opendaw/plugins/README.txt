OpenDAW Python Plugins

Create a .py file containing NAME, optional DESCRIPTION, and register(app).
Example:

NAME = 'My Plugin'
DESCRIPTION = 'Does something useful'

def register(app):
    app.register_plugin_command('Hello', lambda: print('Hello from OpenDAW'))
