from pythonanywhere.deploy import deploy

deploy(
    username="analistamarvio",
    domain_name="analistamarvio.pythonanywhere.com",
    project_folder="/home/analistamarvio/paradas",
    venv_folder="/home/analistamarvio/paradas/venv",
    wsgi_file="/var/www/analistamarvio_pythonanywhere_com_wsgi.py"
)
