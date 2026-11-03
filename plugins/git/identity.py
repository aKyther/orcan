"""Read the host Git identity without touching credentials or repository config."""
import subprocess


def identity():
    values = {}
    for field, variable in (("name", "GIT_AUTHOR_NAME"), ("email", "GIT_AUTHOR_EMAIL")):
        result = subprocess.run(["git", "config", "--global", "--get", "user." + field], capture_output=True, text=True, check=False)
        values[variable] = result.stdout.strip() if result.returncode == 0 else ""
    return values


if __name__ == '__main__':
    import shlex
    for key, value in identity().items():
        print('export ' + key + '=' + shlex.quote(value))
