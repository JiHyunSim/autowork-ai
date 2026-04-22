export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export interface Database {
  public: {
    Tables: {
      users: {
        Row: {
          id: string
          email: string
          name: string | null
          avatar_url: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id: string
          email: string
          name?: string | null
          avatar_url?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          id?: string
          email?: string
          name?: string | null
          avatar_url?: string | null
          updated_at?: string
        }
      }
      teams: {
        Row: {
          id: string
          name: string
          plan: "starter" | "pro" | "enterprise"
          owner_id: string
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          name: string
          plan?: "starter" | "pro" | "enterprise"
          owner_id: string
          created_at?: string
          updated_at?: string
        }
        Update: {
          name?: string
          plan?: "starter" | "pro" | "enterprise"
          updated_at?: string
        }
      }
      team_members: {
        Row: {
          id: string
          team_id: string
          user_id: string
          role: "owner" | "admin" | "member"
          created_at: string
        }
        Insert: {
          id?: string
          team_id: string
          user_id: string
          role?: "owner" | "admin" | "member"
          created_at?: string
        }
        Update: {
          role?: "owner" | "admin" | "member"
        }
      }
      subscriptions: {
        Row: {
          id: string
          team_id: string
          plan: "starter" | "pro" | "enterprise"
          status: "active" | "past_due" | "cancelled" | "trialing"
          toss_customer_key: string | null
          toss_billing_key: string | null
          current_period_start: string | null
          current_period_end: string | null
          trial_end: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          team_id: string
          plan: "starter" | "pro" | "enterprise"
          status?: "active" | "past_due" | "cancelled" | "trialing"
          toss_customer_key?: string | null
          toss_billing_key?: string | null
          current_period_start?: string | null
          current_period_end?: string | null
          trial_end?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          plan?: "starter" | "pro" | "enterprise"
          status?: "active" | "past_due" | "cancelled" | "trialing"
          toss_billing_key?: string | null
          current_period_start?: string | null
          current_period_end?: string | null
          updated_at?: string
        }
      }
      meeting_summaries: {
        Row: {
          id: string
          team_id: string
          created_by: string
          title: string
          original_file_path: string | null
          transcript: string | null
          summary: string | null
          action_items: Json | null
          decisions: Json | null
          status: "uploading" | "transcribing" | "summarizing" | "done" | "failed"
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          team_id: string
          created_by: string
          title: string
          original_file_path?: string | null
          transcript?: string | null
          summary?: string | null
          action_items?: Json | null
          decisions?: Json | null
          status?: "uploading" | "transcribing" | "summarizing" | "done" | "failed"
          created_at?: string
          updated_at?: string
        }
        Update: {
          title?: string
          transcript?: string | null
          summary?: string | null
          action_items?: Json | null
          decisions?: Json | null
          status?: "uploading" | "transcribing" | "summarizing" | "done" | "failed"
          updated_at?: string
        }
      }
      reports: {
        Row: {
          id: string
          team_id: string
          created_by: string
          title: string
          report_type: "weekly" | "daily" | "custom"
          period_start: string | null
          period_end: string | null
          content: string | null
          status: "draft" | "generating" | "done"
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          team_id: string
          created_by: string
          title: string
          report_type?: "weekly" | "daily" | "custom"
          period_start?: string | null
          period_end?: string | null
          content?: string | null
          status?: "draft" | "generating" | "done"
          created_at?: string
          updated_at?: string
        }
        Update: {
          title?: string
          content?: string | null
          status?: "draft" | "generating" | "done"
          updated_at?: string
        }
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
  }
}
