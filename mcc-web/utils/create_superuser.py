#!/usr/bin/env python3
"""
Create a Django superuser programmatically.

This script can be used after a database reset to create an admin user.
"""

import os
import sys
import getpass
from pathlib import Path


def create_superuser(
    username: str,
    email: str = '',
    password: str = None,
    project_dir: Path = None
) -> bool:
    """
    Create a Django superuser.
    
    Args:
        username: Username for the superuser
        email: Email address (optional)
        password: Password (if None, will prompt)
        project_dir: Project root directory
    
    Returns:
        True if user was created, False otherwise
    """
    if project_dir is None:
        # Get project root directory (parent of utils/)
        project_dir = Path(__file__).parent.parent
    
    try:
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        sys.path.insert(0, str(project_dir))
        
        import django
        django.setup()
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Check if user already exists
        if User.objects.filter(username=username).exists():
            print(f"User '{username}' already exists!")
            response = input("Do you want to change the password? (yes/no): ")
            if response.lower() == 'yes':
                if password is None:
                    password = getpass.getpass("Enter new password: ")
                    password_confirm = getpass.getpass("Confirm password: ")
                    if password != password_confirm:
                        print("Passwords do not match!")
                        return False
                
                user = User.objects.get(username=username)
                user.set_password(password)
                user.is_superuser = True
                user.is_staff = True
                user.save()
                print(f"✓ Password updated for user '{username}'")
                return True
            return False
        
        # Get password if not provided
        if password is None:
            password = getpass.getpass("Enter password: ")
            password_confirm = getpass.getpass("Confirm password: ")
            if password != password_confirm:
                print("Passwords do not match!")
                return False
        
        # Create superuser
        User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        
        print(f"✓ Superuser '{username}' created successfully!")
        return True
        
    except Exception as e:
        print(f"✗ Error creating superuser: {e}")
        import traceback
        traceback.print_exc()
        return False


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Create a Django superuser'
    )
    parser.add_argument(
        '--username',
        type=str,
        default='admin',
        help='Username for the superuser (default: admin)'
    )
    parser.add_argument(
        '--email',
        type=str,
        default='',
        help='Email address (optional)'
    )
    parser.add_argument(
        '--password',
        type=str,
        default=None,
        help='Password (if not provided, will prompt)'
    )
    parser.add_argument(
        '--project-dir',
        type=str,
        default=None,
        help='Project root directory (default: auto-detect from script location)'
    )
    
    args = parser.parse_args()
    
    # Default to project root (parent of utils/)
    project_dir = Path(args.project_dir) if args.project_dir else Path(__file__).parent.parent
    
    try:
        success = create_superuser(
            username=args.username,
            email=args.email,
            password=args.password,
            project_dir=project_dir
        )
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())

