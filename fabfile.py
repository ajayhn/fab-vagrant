import os
import sys
import string
import netaddr

from fabric.api import task
from fabric.operations import local, run, put
from fabric.context_managers import settings, lcd, cd

_PKGS_BOX_VFILE_TEMPL = string.Template("""
Vagrant.configure("2") do |config|

  # If you are still using old centos box, you have to setup root username for
  # ssh access. Read more in section 'SSH Access To VM'.
  config.ssh.username = "root"

  config.vm.define :$__vm_name__ do |$__vm_name__|
    $__vm_name__.vm.box = "$__base_box__"
    $__vm_name__.vm.network :private_network, :ip => '$__ip__'
    $__vm_name__.vm.provider :libvirt do |domain|
      domain.memory = 4096
      domain.cpus = 2
      domain.nested = true
      domain.volume_cache = 'none'
    end
  end

  config.vm.provider :libvirt do |libvirt|
    libvirt.driver = "qemu"
    libvirt.host = "localhost"
    libvirt.connect_via_ssh = true
    libvirt.username = "root"
    libvirt.storage_pool_name = "default"
  end
end
""")

_VFILE_EMBED_TEMPL = string.Template("""
Vagrant.configure("2") do |config|

  # If you are still using old centos box, you have to setup root username for
  # ssh access. Read more in section 'SSH Access To VM'.
  config.ssh.username = "root"

  config.vm.provider :libvirt do |libvirt|
    libvirt.driver = "qemu"
    libvirt.host = "localhost"
    libvirt.connect_via_ssh = true
    libvirt.username = "root"
    libvirt.storage_pool_name = "default"
  end
end
""")

_METADATA_JSON_TEMPL = string.Template("""
{
  "provider"     : "libvirt",
  "format"       : "qcow2",
  "virtual_size" : 40
}
""")

_ROLE_BOX_VFILE_TEMPL = string.Template("""
Vagrant.configure("2") do |config|

  # If you are still using old centos box, you have to setup root username for
  # ssh access. Read more in section 'SSH Access To VM'.
  config.ssh.username = "root"

  config.vm.define :$__vm_name__ do |$__vm_name__|
    $__vm_name__.vm.box = "$__base_box__"
    $__vm_name__.vm.network :private_network, :ip => '$__ip__'
    $__vm_name__.vm.hostname = "$__hostname__"
    $__vm_name__.vm.provider :libvirt do |domain|
      domain.memory = 4096
      domain.cpus = 2
      domain.nested = true
      domain.volume_cache = 'none'
    end
  end

  config.vm.provider :libvirt do |libvirt|
    libvirt.driver = "qemu"
    libvirt.host = "localhost"
    libvirt.connect_via_ssh = true
    libvirt.username = "root"
    libvirt.storage_pool_name = "default"
  end
end
""")

def _template_substitute(template, vals):
    data = template.safe_substitute(vals)
    return data
#end _template_substitute

def _template_substitute_write(template, vals, filename):
    data = _template_substitute(template, vals)
    outfile = open(filename, 'w')
    outfile.write(data)
    outfile.close()
#end _template_substitute_write

@task
def vagrant_create_base_box(build_num=None, distro='centos', ip='10.20.30.40'):
    if not build_num:
        print "build_num mandatory"
        sys.exit(1)

    # create base box (with build packages installed) definition
    fq_name = "%s_%s" %(distro, build_num)
    box_dir = "%s_box" %(fq_name)
    vm_name = "%s_vm" %(fq_name)
    vm_qcow2_path = "/var/lib/libvirt/images/%s_%s.img" %(box_dir, vm_name)
    if distro == 'centos':
        pkgs_name = "contrail-install-packages-1.03-%s.el6.noarch.rpm" %(build_num)
        pkgs_url = "http://10.84.5.100/cs-shared/builder/centos64_os/%s/%s" %(build_num, pkgs_name)
    else:
        print "Unsupported distro"
        sys.exit(1)

    if not os.path.exists(box_dir):
        local("mkdir %s" %(box_dir))

    with lcd(box_dir):
        _template_substitute_write(_PKGS_BOX_VFILE_TEMPL,
            {'__vm_name__': vm_name, '__ip__': ip,
             '__base_box__': "centos64"},
            '%s/Vagrantfile' %(box_dir))

        local("vagrant up --provider=libvirt")
        with settings(host_string='root@%s' %(ip), password='vagrant'):
            run("wget %s" %(pkgs_url))
            run("yum --disablerepo=* -y localinstall %s" %(pkgs_name))
            with cd("/opt/contrail/contrail_packages"):
                run("./setup.sh")
                import pdb; pdb.set_trace()
                run("pip-python install --upgrade /opt/contrail/contrail_installer/contrail_setup_utils/pycrypto-2.6.tar.gz")
                run("pip-python install --upgrade /opt/contrail/contrail_installer/contrail_setup_utils/paramiko-1.11.0.tar.gz")
                run("pip-python install --upgrade --no-deps /opt/contrail/contrail_installer/contrail_setup_utils/Fabric-1.7.0.tar.gz")

            with settings(warn_only=True):
                run("mv /lib/udev/write_net_rules /tmp")
                run("rm /etc/udev/rules.d/70-persistent-net.rules")
            pass
        local("vagrant halt")
        local("cp %s box.img" %(vm_qcow2_path))
        _template_substitute_write(_VFILE_EMBED_TEMPL, {}, '%s/Vagrantfile.installed' %(box_dir))
        _template_substitute_write(_METADATA_JSON_TEMPL, {}, '%s/metadata.json' %(box_dir))
        local("tar cvfz %s_pkgs.box ./metadata.json ./Vagrantfile.installed ./box.img" %(fq_name))
        local("vagrant box add %s_pkgs %s_pkgs.box --provider libvirt" %(fq_name, fq_name))

#end vagrant_create_base_box

def _create_role_box(role, build_num, distro, ip):
    if not build_num:
        print "build_num mandatory"
        sys.exit(1)

    # create base box (with build packages installed) definition
    fq_name = "%s_%s_%s" %(distro, build_num, role)
    if role == 'pkgs':
        base_box = "centos64"
    else:
        base_box = "%s_%s_pkgs" %(distro, build_num)

    box_dir = "%s_box" %(fq_name)
    vm_name = "%s_vm" %(fq_name)
    vm_qcow2_path = "/var/lib/libvirt/images/%s_%s.img" %(box_dir, vm_name)
    if distro == 'centos':
        pass
    else:
        print "Unsupported distro"
        sys.exit(1)

    if not os.path.exists(box_dir):
        local("mkdir %s" %(box_dir))

    with lcd(box_dir):
        _template_substitute_write(_ROLE_BOX_VFILE_TEMPL,
            {'__vm_name__': vm_name, '__ip__': ip,
             '__base_box__': base_box, '__hostname__': role},
            '%s/Vagrantfile' %(box_dir))

        local("vagrant up --provider=libvirt")
        with settings(host_string='root@%s' %(ip), password='vagrant'):
            if (role == 'pkgs'):
                run("wget %s" %(pkgs_url))
                run("yum --disablerepo=* -y localinstall %s" %(pkgs_name))
                with cd("/opt/contrail/contrail_packages"):
                    run("./setup.sh")
                with settings(warn_only=True):
                    run("mv /lib/udev/write_net_rules /tmp")
                    run("rm /etc/udev/rules.d/70-persistent-net.rules")
            else: # role is not pkgs
                   # create a testbed file to our liking
                with cd("/opt/contrail/utils/fabfile/testbeds"):
                    run("cp testbed_singlebox_example.py testbed.py")
                    run("sed -i -e 's/1.1.1.1/%s/' -e 's/secret/vagrant/' testbed.py" %(ip))
                    run("echo 'env.interface_rename = False' >> testbed.py")

                # install packages for role
                with cd("/opt/contrail/utils"):
                    if role == 'compute':
                        run("pip-python install --upgrade /opt/contrail/contrail_installer/contrail_setup_utils/pycrypto-2.6.tar.gz")
                        run("fab install_vrouter")
                    if role == 'controller':
                        run("pip-python install --upgrade /opt/contrail/contrail_installer/contrail_setup_utils/pycrypto-2.6.tar.gz")
                        run("fab install_database")
                        run("fab install_cfgm")
                        run("fab install_collector")
                        run("fab install_control")
                        run("fab install_webui")
                        run("fab install_openstack")

                    #import pdb; pdb.set_trace()
                    run("pip-python install --upgrade /opt/contrail/contrail_installer/contrail_setup_utils/pycrypto-2.6.tar.gz")
                    run("pip-python install --upgrade /opt/contrail/contrail_installer/contrail_setup_utils/paramiko-1.11.0.tar.gz")
                    run("pip-python install --upgrade --no-deps /opt/contrail/contrail_installer/contrail_setup_utils/Fabric-1.7.0.tar.gz")
            
        local("vagrant halt")
        local("cp %s box.img" %(vm_qcow2_path))
        _template_substitute_write(_VFILE_EMBED_TEMPL, {}, '%s/Vagrantfile.installed' %(box_dir))
        _template_substitute_write(_METADATA_JSON_TEMPL, {}, '%s/metadata.json' %(box_dir))
        local("tar cvfz %s.box ./metadata.json ./Vagrantfile.installed ./box.img" %(fq_name))
        local("vagrant box add %s %s.box --provider libvirt" %(fq_name, fq_name))
#end _create_role_box

@task
def vagrant_create_controller_box(build_num=None, distro='centos', ip = '10.20.30.40'):
    _create_role_box('controller', build_num, distro, ip)
#end vagrant_create_controller_box

@task
def vagrant_create_compute_box(build_num=None, distro='centos', ip = '10.20.30.40'):
    _create_role_box('compute', build_num, distro, ip)
#end vagrant_create_compute_box

@task
def vagrant_create_cluster(build_num=None, distro='centos', ip='10.20.30.40',
                           testbed_py='testbed', name='cluster'):
    if not build_num:
        print "build_num mandatory"
        sys.exit(1)

    if distro == 'centos':
        pass
    else:
        print "Unsupported distro"
        sys.exit(1)

    # read in testbed definition file
    sys.path.insert(0, '.')
    testbed = __import__(testbed_py)
    ncontrollers = len(testbed.env.roledefs['cfgm'])
    ncomputes = len(testbed.env.roledefs['compute'])

    controller_base_box = "%s_%s_controller" %(distro, build_num)
    compute_base_box = "%s_%s_compute" %(distro, build_num)

    cluster_dir = '%s_%s_%s' %(name, distro, build_num)
    if not os.path.exists(cluster_dir):
        local("mkdir %s" %(cluster_dir))

    with lcd(cluster_dir):
        # create controller VMs
        for i in range(ncontrollers):
            vm_dir = 'controller%s' %(i)
            vm_name = 'controller%s' %(i)
            if not os.path.exists('%s/%s' %(cluster_dir, vm_dir)):
                local("mkdir %s" %(vm_dir))

            with lcd(vm_dir):
                host_str = testbed.env.roledefs['cfgm'][i]
                host_passwd = testbed.env.passwords[host_str]
                ip_addr = host_str.split('@')[1]
                _template_substitute_write(_ROLE_BOX_VFILE_TEMPL,
                    {'__vm_name__': vm_name, '__ip__': ip_addr,
                     '__base_box__': controller_base_box, '__hostname__': vm_name},
                    '%s/%s/Vagrantfile' %(cluster_dir, vm_dir))

                local("vagrant up --provider=libvirt")
                local("vagrant ssh -c 'service network restart'")

        # create compute VMs
        for i in range(ncomputes):
            vm_dir = 'compute%s' %(i)
            vm_name = 'compute%s' %(i)
            if not os.path.exists('%s/%s' %(cluster_dir, vm_dir)):
                local("mkdir %s" %(vm_dir))

            with lcd(vm_dir):
                host_str = testbed.env.roledefs['compute'][i]
                host_passwd = testbed.env.passwords[host_str]
                ip_addr = host_str.split('@')[1]
                _template_substitute_write(_ROLE_BOX_VFILE_TEMPL,
                    {'__vm_name__': vm_name, '__ip__': str(ip_addr),
                     '__base_box__': compute_base_box, '__hostname__': vm_name},
                    '%s/%s/Vagrantfile' %(cluster_dir, vm_dir))

                local("vagrant up --provider=libvirt")
                local("vagrant ssh -c 'service network restart'")

        # put testbed.py on first controller and run setup_all
        first_cfgm = testbed.env.roledefs['cfgm'][0]
        with settings(host_string=first_cfgm, password='vagrant'):
            with cd("/opt/contrail/utils/fabfile/testbeds"):
                put('../%s.py' %(testbed_py), "testbed.py")
                run("sed -i -e 's/secret/vagrant/' testbed.py")
                run("echo 'env.interface_rename = False' >> testbed.py")

            with cd("/opt/contrail/utils"):
                import pdb; pdb.set_trace()
                run("fab setup_all")

#end vagrant_create_cluster
