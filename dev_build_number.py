# DO NOT CHANGE THE FOLLOWING LINE MANUALLY!
BUILD_NUMBER = 26

# XXX: THIS IS A WONDERFUL, TERRIBLE HACK. ABSOLUTELY REMOVE THIS BEFORE ANYONE SEES IT.
import socket
if socket.gethostname() in ('DEDHAM',):
    try:
        import git
        buildnum = len(git.Repo('.').log())
        if BUILD_NUMBER != buildnum:
            BUILD_NUMBER = buildnum
            with open(__file__, 'rb') as f:
                f.readline()
                f.readline()
                contents = f.read()
            with open(__file__, 'wb') as f:
                f.write('# DO NOT CHANGE THE FOLLOWING LINE MANUALLY!\n')
                f.write('BUILD_NUMBER = %d\n' % BUILD_NUMBER)
                f.write(contents)
    except (ImportError, git.errors.GitCommandError):
        pass