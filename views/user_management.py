import streamlit as st
from database import get_db_session, User
from utils.auth import (
    require_admin, hash_password, ROLES, ALL_PAGES, 
    get_current_user
)
from utils.translations import t
from datetime import datetime


def render():
    require_admin()
    
    st.title("User Management")
    st.caption("Manage user accounts and access permissions")
    
    tab1, tab2 = st.tabs(["Users", "Add New User"])
    
    with tab1:
        render_user_list()
    
    with tab2:
        render_add_user_form()


def render_user_list():
    with get_db_session() as session:
        users = session.query(User).order_by(User.username).all()
        
        if not users:
            st.info("No users found.")
            return
        
        current_user = get_current_user()
        
        for user in users:
            with st.expander(f"{'🟢' if user.is_active else '🔴'} {user.username} ({user.role})", expanded=False):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Full Name:** {user.full_name or '-'}")
                    st.write(f"**Email:** {user.email or '-'}")
                    st.write(f"**Role:** {ROLES.get(user.role, {}).get('name', user.role)}")
                    st.write(f"**Status:** {'Active' if user.is_active else 'Inactive'}")
                
                with col2:
                    st.write(f"**Created:** {user.created_at.strftime('%Y-%m-%d %H:%M')}")
                    if user.last_login:
                        st.write(f"**Last Login:** {user.last_login.strftime('%Y-%m-%d %H:%M')}")
                    else:
                        st.write("**Last Login:** Never")
                    
                    allowed = user.allowed_pages or ''
                    if allowed == 'all':
                        st.write("**Access:** All pages")
                    else:
                        pages = [p.strip() for p in allowed.split(',') if p.strip()]
                        st.write(f"**Access:** {len(pages)} page(s)")
                
                st.markdown("---")
                
                is_self = current_user and current_user['id'] == user.id
                
                col_edit1, col_edit2, col_edit3 = st.columns([2, 2, 1])
                
                with col_edit1:
                    new_role = st.selectbox(
                        "Role",
                        options=list(ROLES.keys()),
                        index=list(ROLES.keys()).index(user.role) if user.role in ROLES else 0,
                        key=f"role_{user.id}",
                        disabled=is_self
                    )
                
                with col_edit2:
                    new_status = st.checkbox(
                        "Active",
                        value=user.is_active,
                        key=f"active_{user.id}",
                        disabled=is_self
                    )
                
                with col_edit3:
                    if st.button("Update", key=f"update_{user.id}", disabled=is_self):
                        user.role = new_role
                        user.is_active = new_status
                        if new_role == 'admin':
                            user.allowed_pages = 'all'
                        else:
                            user.allowed_pages = ROLES.get(new_role, {}).get('default_pages', '')
                        user.updated_at = datetime.utcnow()
                        session.commit()
                        st.success(f"User {user.username} updated.")
                        st.rerun()
                
                st.markdown("##### Page Access")
                allowed_pages = user.allowed_pages or ''
                if allowed_pages == 'all':
                    allowed_list = [p[0] for p in ALL_PAGES]
                else:
                    allowed_list = [p.strip() for p in allowed_pages.split(',')]
                
                page_cols = st.columns(3)
                new_allowed = []
                for i, (page_id, page_name) in enumerate(ALL_PAGES):
                    with page_cols[i % 3]:
                        if st.checkbox(
                            page_name,
                            value=page_id in allowed_list or allowed_pages == 'all',
                            key=f"page_{user.id}_{page_id}",
                            disabled=user.role == 'admin'
                        ):
                            new_allowed.append(page_id)
                
                col_save, col_delete = st.columns([3, 1])
                with col_save:
                    if st.button("Save Permissions", key=f"save_perms_{user.id}", disabled=user.role == 'admin'):
                        user.allowed_pages = ','.join(new_allowed)
                        user.updated_at = datetime.utcnow()
                        session.commit()
                        st.success("Permissions saved.")
                        st.rerun()
                
                with col_delete:
                    if not is_self and user.username not in ['admin', 'demo']:
                        if st.button("🗑️ Delete", key=f"delete_{user.id}", type="secondary"):
                            session.delete(user)
                            session.commit()
                            st.success(f"User {user.username} deleted.")
                            st.rerun()
                
                st.markdown("##### Change Password")
                pwd_col1, pwd_col2, pwd_col3 = st.columns([2, 2, 1])
                with pwd_col1:
                    new_password = st.text_input(
                        "New Password",
                        type="password",
                        placeholder="Enter new password",
                        key=f"new_pwd_{user.id}"
                    )
                with pwd_col2:
                    confirm_new_password = st.text_input(
                        "Confirm Password",
                        type="password",
                        placeholder="Confirm password",
                        key=f"confirm_pwd_{user.id}"
                    )
                with pwd_col3:
                    st.write("")
                    st.write("")
                    if st.button("Change", key=f"change_pwd_{user.id}"):
                        if not new_password:
                            st.error("Please enter a new password.")
                        elif len(new_password) < 6:
                            st.error("Password must be at least 6 characters.")
                        elif new_password != confirm_new_password:
                            st.error("Passwords do not match.")
                        else:
                            user.password_hash = hash_password(new_password)
                            user.updated_at = datetime.utcnow()
                            session.commit()
                            st.success(f"Password changed for {user.username}.")
                            st.rerun()


def render_add_user_form():
    st.subheader("Create New User")
    
    with st.form("add_user_form"):
        username = st.text_input("Username *", placeholder="Enter username")
        password = st.text_input("Password *", type="password", placeholder="Enter password")
        confirm_password = st.text_input("Confirm Password *", type="password", placeholder="Confirm password")
        
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name", placeholder="Enter full name")
        with col2:
            email = st.text_input("Email", placeholder="Enter email")
        
        role = st.selectbox(
            "Role",
            options=list(ROLES.keys()),
            format_func=lambda x: f"{ROLES[x]['name']} - {ROLES[x]['description']}"
        )
        
        st.markdown("##### Page Access")
        st.caption("Select which pages this user can access")
        
        default_pages = ROLES.get(role, {}).get('default_pages', '')
        if default_pages == 'all':
            default_list = [p[0] for p in ALL_PAGES]
        else:
            default_list = [p.strip() for p in default_pages.split(',')]
        
        page_cols = st.columns(3)
        selected_pages = []
        for i, (page_id, page_name) in enumerate(ALL_PAGES):
            with page_cols[i % 3]:
                if st.checkbox(page_name, value=page_id in default_list, key=f"new_page_{page_id}"):
                    selected_pages.append(page_id)
        
        submit = st.form_submit_button("Create User", type="primary")
        
        if submit:
            if not username or not password:
                st.error("Username and password are required.")
            elif password != confirm_password:
                st.error("Passwords do not match.")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                with get_db_session() as session:
                    existing = session.query(User).filter(User.username == username).first()
                    if existing:
                        st.error(f"Username '{username}' already exists.")
                    else:
                        new_user = User(
                            username=username,
                            password_hash=hash_password(password),
                            full_name=full_name,
                            email=email,
                            role=role,
                            is_active=True,
                            allowed_pages='all' if role == 'admin' else ','.join(selected_pages)
                        )
                        session.add(new_user)
                        session.commit()
                        st.success(f"User '{username}' created successfully!")
                        st.rerun()
