"""exec the actual engine with no API credential in its environment."""
import os
import sys
from integration.environment import subscription_environment
if __name__=='__main__':
    os.execve(sys.executable,[sys.executable,'-m','integration.engine_server'],subscription_environment())
