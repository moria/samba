# functions to support bundled libraries

import sys
import Build, Options, Logs
from Configure import conf
from samba_utils import TO_LIST

def PRIVATE_NAME(bld, name, private_extension, private_library):
    '''possibly rename a library to include a bundled extension'''

    if not private_library:
        return name

    # we now use the same private name for libraries as the public name.
    # see http://git.samba.org/?p=tridge/junkcode.git;a=tree;f=shlib for a
    # demonstration that this is the right thing to do
    # also see http://lists.samba.org/archive/samba-technical/2011-January/075816.html
    if private_extension:
        return name

    extension = bld.env.PRIVATE_EXTENSION

    if extension and name.startswith('%s' % extension):
        return name

    if extension and name.endswith('%s' % extension):
        return name

    return "%s-%s" % (name, extension)


def target_in_list(target, lst, default):
    for l in lst:
        if target == l:
            return True
        if '!' + target == l:
            return False
        if l == 'ALL':
            return True
        if l == 'NONE':
            return False
    return default


def BUILTIN_LIBRARY(bld, name):
    '''return True if a library should be builtin
       instead of being built as a shared lib'''
    return target_in_list(name, bld.env.BUILTIN_LIBRARIES, False)
Build.BuildContext.BUILTIN_LIBRARY = BUILTIN_LIBRARY


def BUILTIN_DEFAULT(opt, builtins):
    '''set a comma separated default list of builtin libraries for this package'''
    if 'BUILTIN_LIBRARIES_DEFAULT' in Options.options:
        return
    Options.options['BUILTIN_LIBRARIES_DEFAULT'] = builtins
Options.Handler.BUILTIN_DEFAULT = BUILTIN_DEFAULT


def PRIVATE_EXTENSION_DEFAULT(opt, extension, noextension=''):
    '''set a default private library extension'''
    if 'PRIVATE_EXTENSION_DEFAULT' in Options.options:
        return
    Options.options['PRIVATE_EXTENSION_DEFAULT'] = extension
    Options.options['PRIVATE_EXTENSION_EXCEPTION'] = noextension
Options.Handler.PRIVATE_EXTENSION_DEFAULT = PRIVATE_EXTENSION_DEFAULT


def minimum_library_version(conf, libname, default):
    '''allow override of mininum system library version'''

    minlist = Options.options.MINIMUM_LIBRARY_VERSION
    if not minlist:
        return default

    for m in minlist.split(','):
        a = m.split(':')
        if len(a) != 2:
            Logs.error("Bad syntax for --minimum-library-version of %s" % m)
            sys.exit(1)
        if a[0] == libname:
            return a[1]
    return default


@conf
def LIB_MAY_BE_BUNDLED(conf, libname):
    if libname in conf.env.BUNDLED_LIBS:
        return True
    if '!%s' % libname in conf.env.BUNDLED_LIBS:
        return False
    if 'NONE' in conf.env.BUNDLED_LIBS:
        return False
    return True

@conf
def LIB_MUST_BE_BUNDLED(conf, libname):
    if libname in conf.env.BUNDLED_LIBS:
        return True
    if '!%s' % libname in conf.env.BUNDLED_LIBS:
        return False
    if 'ALL' in conf.env.BUNDLED_LIBS:
        return True
    return False

@conf
def LIB_MUST_BE_PRIVATE(conf, libname):
    return ('ALL' in conf.env.PRIVATE_LIBS or
            libname in conf.env.PRIVATE_LIBS)

@conf
def CHECK_BUNDLED_SYSTEM_PKG(conf, libname, minversion='0.0.0',
        maxversion=None, version_blacklist=[],
        onlyif=None, implied_deps=None, pkg=None):
    '''check if a library is available as a system library.

    This only tries using pkg-config
    '''
    return conf.CHECK_BUNDLED_SYSTEM(libname,
                                     minversion=minversion,
                                     maxversion=maxversion,
                                     version_blacklist=version_blacklist,
                                     onlyif=onlyif,
                                     implied_deps=implied_deps,
                                     pkg=pkg)

@conf
def CHECK_BUNDLED_SYSTEM(conf, libname, minversion='0.0.0',
                         maxversion=None, version_blacklist=[],
                         checkfunctions=None, headers=None, checkcode=None,
                         onlyif=None, implied_deps=None,
                         require_headers=True, pkg=None, set_target=True):
    '''check if a library is available as a system library.
    this first tries via pkg-config, then if that fails
    tries by testing for a specified function in the specified lib
    '''
    # We always do a logic validation of 'onlyif' first
    missing = []
    if onlyif:
        for l in TO_LIST(onlyif):
            f = 'FOUND_SYSTEMLIB_%s' % l
            if not f in conf.env:
                Logs.error('ERROR: CHECK_BUNDLED_SYSTEM(%s) - ' % (libname) +
                           'missing prerequisite check for ' +
                           'system library %s, onlyif=%r' % (l, onlyif))
                sys.exit(1)
            if not conf.env[f]:
                missing.append(l)
    found = 'FOUND_SYSTEMLIB_%s' % libname
    if found in conf.env:
        return conf.env[found]
    if conf.LIB_MUST_BE_BUNDLED(libname):
        conf.env[found] = False
        return False

    # see if the library should only use a system version if another dependent
    # system version is found. That prevents possible use of mixed library
    # versions
    if missing:
        if not conf.LIB_MAY_BE_BUNDLED(libname):
            Logs.error('ERROR: Use of system library %s depends on missing system library/libraries %r' % (libname, missing))
            sys.exit(1)
        conf.env[found] = False
        return False

    def check_functions_headers_code():
        '''helper function for CHECK_BUNDLED_SYSTEM'''
        if require_headers and headers and not conf.CHECK_HEADERS(headers, lib=libname):
            return False
        if checkfunctions is not None:
            ok = conf.CHECK_FUNCS_IN(checkfunctions, libname, headers=headers,
                                     empty_decl=False, set_target=False)
            if not ok:
                return False
        if checkcode is not None:
            define='CHECK_BUNDLED_SYSTEM_%s' % libname.upper()
            ok = conf.CHECK_CODE(checkcode, lib=libname,
                                 headers=headers, local_include=False,
                                 msg=msg, define=define)
            conf.CONFIG_RESET(define)
            if not ok:
                return False
        return True

    minversion = minimum_library_version(conf, libname, minversion)

    msg = 'Checking for system %s' % libname
    msg_ver = []
    if minversion != '0.0.0':
        msg_ver.append('>=%s' % minversion)
    if maxversion is not None:
        msg_ver.append('<=%s' % maxversion)
    for v in version_blacklist:
        msg_ver.append('!=%s' % v)
    if msg_ver != []:
        msg += " (%s)" % (" ".join(msg_ver))

    uselib_store=libname.upper()
    if pkg is None:
        pkg = libname

    version_checks = '%s >= %s' % (pkg, minversion)
    if maxversion is not None:
        version_checks += ' %s <= %s' % (pkg, maxversion)
    for v in version_blacklist:
        version_checks += ' %s != %s' % (pkg, v)

    # try pkgconfig first
    if (conf.CHECK_CFG(package=pkg,
                      args='"%s" --cflags --libs' % (version_checks),
                      msg=msg, uselib_store=uselib_store) and
        check_functions_headers_code()):
        if set_target:
            conf.SET_TARGET_TYPE(libname, 'SYSLIB')
        conf.env[found] = True
        if implied_deps:
            conf.SET_SYSLIB_DEPS(libname, implied_deps)
        return True
    if checkfunctions is not None:
        if check_functions_headers_code():
            conf.env[found] = True
            if implied_deps:
                conf.SET_SYSLIB_DEPS(libname, implied_deps)
            if set_target:
                conf.SET_TARGET_TYPE(libname, 'SYSLIB')
            return True
    conf.env[found] = False
    if not conf.LIB_MAY_BE_BUNDLED(libname):
        Logs.error('ERROR: System library %s of version %s not found, and bundling disabled' % (libname, minversion))
        sys.exit(1)
    return False


def tuplize_version(version):
    return tuple([int(x) for x in version.split(".")])

@conf
def CHECK_BUNDLED_SYSTEM_PYTHON(conf, libname, modulename, minversion='0.0.0'):
    '''check if a python module is available on the system and
    has the specified minimum version.
    '''
    if conf.LIB_MUST_BE_BUNDLED(libname):
        return False

    # see if the library should only use a system version if another dependent
    # system version is found. That prevents possible use of mixed library
    # versions
    minversion = minimum_library_version(conf, libname, minversion)

    try:
        m = __import__(modulename)
    except ImportError:
        found = False
    else:
        try:
            version = m.__version__
        except AttributeError:
            found = False
        else:
            found = tuplize_version(version) >= tuplize_version(minversion)
    if not found and not conf.LIB_MAY_BE_BUNDLED(libname):
        Logs.error('ERROR: Python module %s of version %s not found, and bundling disabled' % (libname, minversion))
        sys.exit(1)
    return found


def NONSHARED_BINARY(bld, name):
    '''return True if a binary should be built without non-system shared libs'''
    return target_in_list(name, bld.env.NONSHARED_BINARIES, False)
Build.BuildContext.NONSHARED_BINARY = NONSHARED_BINARY


