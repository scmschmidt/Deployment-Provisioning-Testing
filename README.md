# Deployment-Provisioning-Testing

Guessing from the unimaginative name, this project is about providing landscapes for testing purposes.
It is primarily driven by the need to have a flexible way to maintain a testing infrastructure for saptune (https://github.com/SUSE/saptune) testing during development.

**THIS IS IN AN EARLY STAGE OF DEVELOPMENT AND NOT READY FOR USE! EVERTHING MAY CHANGE!**

## Deployment

The deployment part takes care of providing the infrastructure (the test machines). To deploy them on libvirt/KVM, AWS and Azure (GCP might follow) the 'simple_deployment' project 
(https://github.com/scmschmidt/simple_deployment) is used. To include existing bare metal machines, a "fake deployment" is used.

## Provisioning

The provisioning part will use Ansible to prepare the hosts for the upcoming testing purposes.


## Testing

TBD


# Installation


pip3 install readchar


- Clone this repo on your machine: `git clone ...`
  The directory must not necessarily your project directory. It can be used as source for
  multiple projects, therefore something like `~/bin` or `/opt` can be used.
  
- Enter the project directory. (e.g. `cd my_project`)

- Initialize DTP by calling `init`. (e.g. `~/bin/Deployment-Provisioning-Testing/init`)

  (This will create a hidden directory '.DTP'.) 
  



