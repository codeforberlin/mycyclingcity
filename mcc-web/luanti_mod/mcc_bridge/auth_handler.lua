-- Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- MCC-controlled Luanti authentication: passwords only from Django (SET_PASSWORD).

local storage = core.get_mod_storage()

local M = {}

M.MSG_NO_REGISTRATION = table.concat({
    "Registrierung und Passwortänderung sind deaktiviert. ",
    "Accounts und Passwörter werden zentral in MyCyclingCity verwaltet ",
    "(Admin: Luanti → Accounts). ",
    "Registration and password changes are disabled; accounts are managed centrally in MCC.",
}, "")

M.MSG_NOT_AUTHORIZED = table.concat({
    "Account nicht freigegeben oder inaktiv in MyCyclingCity. ",
    "Account not authorized or inactive in MCC.",
}, "")

local internal_set_password = false

local function storage_key(prefix, name)
    return prefix .. string.lower(tostring(name or ""))
end

function M.is_provisioned(name)
    if not name or name == "" then
        return false
    end
    return storage:get_string(storage_key("mcc_prov_", name)) == "1"
end

local function mark_provisioned(name, password_hash)
    storage:set_string(storage_key("mcc_prov_", name), "1")
    if password_hash and password_hash ~= "" then
        storage:set_string(storage_key("mcc_pwd_", name), password_hash)
    end
end

local function stored_password_hash(name)
    return storage:get_string(storage_key("mcc_pwd_", name)) or ""
end

function M.clear_provision(name)
    storage:set_string(storage_key("mcc_prov_", name), "")
    storage:set_string(storage_key("mcc_pwd_", name), "")
end

--- Apply plaintext password from Django SET_PASSWORD command.
function M.apply_django_password(pname, raw)
    if not pname or pname == "" or not raw then
        return false
    end
    if not core.get_password_hash or not core.builtin_auth_handler then
        return false
    end
    local hash = core.get_password_hash(pname, tostring(raw))
    internal_set_password = true
    local ok = core.builtin_auth_handler.set_password(pname, hash)
    internal_set_password = false
    if ok then
        mark_provisioned(pname, hash)
        if core.notify_authentication_modified then
            core.notify_authentication_modified(pname)
        end
        core.log("action", "[mcc_bridge] django password provisioned player=" .. pname)
    else
        core.log("error", "[mcc_bridge] django password provision failed player=" .. pname)
    end
    return ok
end

local function delegate_builtin(name, fn_name, ...)
    local builtin = core.builtin_auth_handler
    if not builtin or type(builtin[fn_name]) ~= "function" then
        return false
    end
    return builtin[fn_name](...)
end

core.register_authentication_handler({
    get_auth = function(name)
        if not M.is_provisioned(name) then
            return nil
        end
        return delegate_builtin(name, "get_auth", name)
    end,
    create_auth = function(name, _password)
        core.log("action", "[mcc_bridge] registration denied player=" .. tostring(name))
        return false
    end,
    delete_auth = function(_name)
        return false
    end,
    set_password = function(name, password)
        if internal_set_password then
            local ok = delegate_builtin(name, "set_password", name, password)
            if ok then
                mark_provisioned(name, password)
            end
            return ok
        end
        local stored = stored_password_hash(name)
        if stored ~= "" then
            core.log("action", "[mcc_bridge] blocked client password change player=" .. tostring(name))
            return delegate_builtin(name, "set_password", name, stored)
        end
        return false
    end,
    set_privileges = function(name, privileges)
        if not M.is_provisioned(name) then
            return false
        end
        return delegate_builtin(name, "set_privileges", name, privileges)
    end,
    reload = function()
        return delegate_builtin(nil, "reload")
    end,
    record_login = function(name)
        if not M.is_provisioned(name) then
            return false
        end
        return delegate_builtin(name, "record_login", name)
    end,
})

return M
