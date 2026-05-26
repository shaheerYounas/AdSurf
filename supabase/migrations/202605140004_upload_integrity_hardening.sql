alter table product_profiles
add constraint product_profiles_id_workspace_id_key unique (id, workspace_id);

alter table uploads
drop constraint uploads_product_id_fkey;

alter table uploads
add constraint uploads_product_workspace_fk
foreign key (product_id, workspace_id)
references product_profiles(id, workspace_id)
on delete restrict;

comment on constraint uploads_product_workspace_fk on uploads is
    'Prevents upload metadata from referencing a product owned by a different workspace.';
